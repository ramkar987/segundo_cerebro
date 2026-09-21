import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Item, ProcessingJob
from .analysis import AnalysisSkipped, analyze_item
from .extractors import extract_video_metadata, extract_webpage
from .instagram_images import (
    InstagramImageExtractionError,
    extract_instagram_post,
    extract_visual_text,
)
from .relations import RelationDiscoverySkipped, discover_relations
from .semantic import SemanticIndexSkipped, index_item
from .transcription import (
    TranscriptionSkipped,
    mark_transcription_state,
    transcribe_item,
)


def _set_progress(item: Item, progress: int, stage: str, status=None) -> None:
    item.processing_progress = max(0, min(int(progress), 100))
    item.processing_stage = stage[:160]
    fields = ['processing_progress', 'processing_stage', 'updated_at']
    if status is not None:
        item.status = status
        fields.append('status')
    item.save(update_fields=fields)


def claim_next_job():
    with transaction.atomic():
        job = (
            ProcessingJob.objects.select_for_update(skip_locked=True)
            .filter(state=ProcessingJob.State.PENDING)
            .order_by('created_at')
            .first()
        )
        if not job:
            return None
        job.state = ProcessingJob.State.RUNNING
        job.started_at = timezone.now()
        job.attempts += 1
        job.save(update_fields=['state', 'started_at', 'attempts'])
        return job


def _short_title(text: str, limit: int = 82) -> str:
    clean = ' '.join((text or '').split()).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit + 1].rsplit(' ', 1)[0].rstrip(' ,.;:-')
    return (cut or clean[:limit]).rstrip() + '…'


def _useful_instagram_title(raw_title: str, caption: str) -> str:
    title = (raw_title or '').strip()
    generic = title.lower().startswith('video by ') or title.lower().startswith('photo by ')

    if title and not generic:
        return _short_title(title)

    for line in (caption or '').splitlines():
        candidate = ' '.join(line.split()).strip()
        if candidate and not candidate.startswith('#') and candidate != '.':
            return _short_title(candidate)

    return 'Instagram'


def _try_transcription(item: Item) -> None:
    if not settings.TRANSCRIBE_MEDIA:
        _set_progress(item, 65, 'Transcrição desativada; seguindo')
        return

    try:
        transcribe_item(
            item,
            progress=lambda value, label: _set_progress(item, value, label),
        )
    except TranscriptionSkipped as exc:
        mark_transcription_state(item, 'skipped', str(exc))
        _set_progress(item, 65, 'Transcrição pulada; seguindo')
    except Exception as exc:
        # Metadados/legenda continuam válidos mesmo que a transcrição falhe.
        mark_transcription_state(item, 'error', str(exc))
        _set_progress(item, 65, 'Transcrição falhou; seguindo com a legenda')


def queue_analysis(item: Item) -> bool:
    if not settings.ANALYZE_CONTENT or not settings.GROQ_API_KEY:
        return False

    if item.analysis:
        return queue_relations(item)

    existing = (
        item.jobs.filter(
            kind=ProcessingJob.Kind.ANALYZE,
            state__in=[
                ProcessingJob.State.PENDING,
                ProcessingJob.State.RUNNING,
            ],
        )
        .exists()
    )
    if existing:
        return True

    ProcessingJob.objects.create(
        item=item,
        kind=ProcessingJob.Kind.ANALYZE,
    )
    return True


def queue_relations(item: Item) -> bool:
    if not item.analysis or not settings.GROQ_API_KEY:
        return False

    existing = item.jobs.filter(
        kind=ProcessingJob.Kind.RELATE,
        state__in=[
            ProcessingJob.State.PENDING,
            ProcessingJob.State.RUNNING,
        ],
    ).exists()
    if existing:
        return True

    ProcessingJob.objects.create(
        item=item,
        kind=ProcessingJob.Kind.RELATE,
    )
    return True


def _finish_job(job: ProcessingJob, error: str = '') -> None:
    job.state = ProcessingJob.State.DONE
    job.finished_at = timezone.now()
    job.error = error[:5000]
    job.save(update_fields=['state', 'finished_at', 'error'])


ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def _clean_error(value) -> str:
    return ANSI_ESCAPE_RE.sub('', str(value or '')).strip()


def _fail_job(job: ProcessingJob, exc: Exception) -> None:
    job.state = ProcessingJob.State.ERROR
    job.finished_at = timezone.now()
    job.error = _clean_error(exc)[:5000]
    job.save(update_fields=['state', 'finished_at', 'error'])


def _complete_item(item: Item, stage: str = 'Concluído') -> None:
    """Finaliza sem deixar falha de embeddings invalidar o conteúdo."""
    final_stage = stage

    if settings.SEMANTIC_SEARCH_ENABLED and settings.GEMINI_API_KEY:
        try:
            _set_progress(
                item,
                97,
                'Indexando para busca semântica',
                Item.Status.PROCESSING,
            )
            indexed = index_item(item, force=True)
            if indexed:
                final_stage = f'{stage} · busca semântica pronta'
        except SemanticIndexSkipped:
            pass
        except Exception:
            # index_item registra o erro no metadata da fonte.
            final_stage = f'{stage}; busca semântica pendente'

    _set_progress(item, 100, final_stage, Item.Status.PROCESSED)


def _process_analysis_job(job: ProcessingJob) -> None:
    item = job.item
    _set_progress(item, 75, 'Analisando conteúdo com IA', Item.Status.PROCESSING)

    try:
        analyze_item(item)
        _set_progress(item, 88, 'Análise da IA concluída')
        _finish_job(job)

        # A captura já está pronta para uso após análise + indexação.
        # Descoberta de conexões é enriquecimento e roda em segundo plano.
        _complete_item(item)
        queue_relations(item)

    except AnalysisSkipped as exc:
        _finish_job(job, str(exc))
        _complete_item(item, 'Concluído sem análise da IA')
    except Exception as exc:
        _fail_job(job, exc)
        _set_progress(item, 100, 'Erro na análise da IA', Item.Status.ERROR)
        raise


def _process_relation_job(job: ProcessingJob) -> None:
    item = job.item

    try:
        created = discover_relations(item)
        _finish_job(job, f'{len(created)} conexão(ões) criada(s).')
    except RelationDiscoverySkipped as exc:
        _finish_job(job, str(exc))
    except Exception as exc:
        # Relações são enriquecimento em segundo plano.
        # Falha aqui não altera o estado de uma captura já processada.
        _fail_job(job, exc)


def _process_extract_job(job: ProcessingJob) -> None:
    item = job.item
    _set_progress(item, 10, 'Lendo a fonte', Item.Status.PROCESSING)

    try:
        if item.type in {Item.Type.INSTAGRAM, Item.Type.YOUTUBE}:
            if item.type == Item.Type.INSTAGRAM and '/p/' in item.source_url:
                try:
                    post = extract_instagram_post(item.source_url)
                    data = {
                        'title': post.title,
                        'author': post.author,
                        'description': post.description,
                        'caption': post.caption,
                        'hashtags': post.hashtags,
                        'source_date': post.source_date,
                        'metadata': post.metadata,
                        'image_urls': post.image_urls,
                        'media_kind': post.media_kind,
                        'has_video': post.has_video,
                    }
                except InstagramImageExtractionError as instaloader_exc:
                    # Alguns /p/ são vídeos. Se o leitor de posts falhar,
                    # ainda damos ao yt-dlp a chance de processá-los.
                    try:
                        data = extract_video_metadata(item.source_url)
                        data['image_urls'] = []
                        data['media_kind'] = 'video'
                        data['has_video'] = True
                    except Exception as ytdlp_exc:
                        raise RuntimeError(
                            'Não foi possível ler este post do Instagram. '
                            f'Instaloader: {instaloader_exc}. '
                            f'yt-dlp: {ytdlp_exc}'
                        ) from ytdlp_exc
            else:
                data = extract_video_metadata(item.source_url)
                data['image_urls'] = []
                data['media_kind'] = 'video'
                data['has_video'] = True

            _set_progress(item, 25, 'Metadados e legenda obtidos')

            if item.type == Item.Type.INSTAGRAM:
                item.title = _useful_instagram_title(data['title'], data['caption'])
                item.content = ''
            else:
                item.title = data['title'] or item.title
                item.content = data['description']

            item.source_author = data['author']
            item.source_date = data['source_date']

            source = item.source
            source.caption = data['caption']
            source.description = data['description']
            source.original_hashtags = data['hashtags']
            metadata = dict(source.metadata or {})
            metadata.update(data['metadata'] or {})
            source.metadata = metadata

            if (
                item.type == Item.Type.INSTAGRAM
                and data.get('media_kind') in {'image', 'carousel'}
            ):
                if settings.ANALYZE_IMAGES and data.get('image_urls'):
                    try:
                        visual_text, slides, visual_errors = extract_visual_text(
                            data['image_urls'],
                            progress=lambda value, label: _set_progress(
                                item, value, label
                            ),
                        )
                        item.content = visual_text
                        metadata = dict(source.metadata or {})
                        slides_with_text = sum(
                            1 for slide in slides if slide.get('text')
                        )
                        if visual_errors and slides_with_text:
                            visual_status = 'partial'
                        elif visual_errors:
                            visual_status = 'error'
                        else:
                            visual_status = 'done'

                        providers = sorted(
                            {
                                slide.get('provider')
                                for slide in slides
                                if slide.get('provider')
                            }
                        )
                        metadata['visual_extraction'] = {
                            'status': visual_status,
                            'providers': providers,
                            'groq_model': settings.GROQ_VISION_MODEL,
                            'gemini_model': settings.GEMINI_VISION_MODEL,
                            'slide_count': len(slides),
                            'slides_with_text': slides_with_text,
                            'errors': visual_errors[:10],
                        }
                        source.metadata = metadata

                        if visual_status == 'partial':
                            _set_progress(
                                item,
                                65,
                                'Parte dos slides foi lida; seguindo com o conteúdo obtido',
                            )
                        elif visual_status == 'error':
                            _set_progress(
                                item,
                                65,
                                'Não foi possível ler os slides; seguindo com a legenda',
                            )
                        else:
                            _set_progress(item, 65, 'Texto dos slides extraído')
                    except Exception as exc:
                        # A legenda continua útil; falha visual não invalida a captura.
                        metadata = dict(source.metadata or {})
                        metadata['visual_extraction'] = {
                            'status': 'error',
                            'model': settings.GROQ_VISION_MODEL,
                            'message': _clean_error(exc)[:1000],
                        }
                        source.metadata = metadata
                        _set_progress(
                            item,
                            65,
                            'Não foi possível ler os slides; seguindo com a legenda',
                        )
                else:
                    metadata = dict(source.metadata or {})
                    metadata['visual_extraction'] = {
                        'status': 'skipped',
                        'message': (
                            'Leitura visual desativada.'
                            if not settings.ANALYZE_IMAGES
                            else 'Post sem imagem disponível para leitura.'
                        ),
                    }
                    source.metadata = metadata
                    _set_progress(item, 65, 'Seguindo com a legenda')
            else:
                source.save()
                item.save()
                _try_transcription(item)

            source.save()
            item.save()

        elif item.type == Item.Type.WEB:
            _set_progress(item, 35, 'Extraindo conteúdo da página')
            data = extract_webpage(
                item.source_url,
                timeout=settings.WEB_FETCH_TIMEOUT,
            )
            item.title = data['title'] or item.title
            item.content = data['content']
            item.save()
            _set_progress(item, 65, 'Conteúdo da página obtido')
        else:
            raise ValueError(f'Tipo não processável: {item.type}')

        _finish_job(job)

        if queue_analysis(item):
            _set_progress(item, 70, 'Aguardando análise da IA', Item.Status.PROCESSING)
        else:
            _complete_item(item)

    except Exception as exc:
        _fail_job(job, exc)
        _set_progress(item, 100, 'Erro ao processar a fonte', Item.Status.ERROR)
        raise


def process_job(job: ProcessingJob):
    if job.kind == ProcessingJob.Kind.ANALYZE:
        return _process_analysis_job(job)
    if job.kind == ProcessingJob.Kind.RELATE:
        return _process_relation_job(job)
    return _process_extract_job(job)
