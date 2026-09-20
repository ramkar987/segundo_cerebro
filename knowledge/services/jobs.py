from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Item, ProcessingJob
from .analysis import AnalysisSkipped, analyze_item
from .extractors import extract_video_metadata, extract_webpage
from .relations import RelationDiscoverySkipped, discover_relations
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


def _fail_job(job: ProcessingJob, exc: Exception) -> None:
    job.state = ProcessingJob.State.ERROR
    job.finished_at = timezone.now()
    job.error = str(exc)[:5000]
    job.save(update_fields=['state', 'finished_at', 'error'])


def _process_analysis_job(job: ProcessingJob) -> None:
    item = job.item
    _set_progress(item, 75, 'Analisando conteúdo com IA', Item.Status.PROCESSING)

    try:
        analyze_item(item)
        _set_progress(item, 88, 'Análise da IA concluída')
        _finish_job(job)

        if queue_relations(item):
            _set_progress(item, 92, 'Procurando conteúdos relacionados')
        else:
            _set_progress(item, 100, 'Concluído', Item.Status.PROCESSED)

    except AnalysisSkipped as exc:
        _finish_job(job, str(exc))
        _set_progress(item, 100, 'Concluído sem análise da IA', Item.Status.PROCESSED)
    except Exception as exc:
        _fail_job(job, exc)
        _set_progress(item, 100, 'Erro na análise da IA', Item.Status.ERROR)
        raise


def _process_relation_job(job: ProcessingJob) -> None:
    item = job.item
    _set_progress(item, 94, 'Comparando com a biblioteca', Item.Status.PROCESSING)

    try:
        created = discover_relations(item)
        _finish_job(job, f'{len(created)} relação(ões) sugerida(s).')
        _set_progress(item, 100, 'Concluído', Item.Status.PROCESSED)
    except RelationDiscoverySkipped as exc:
        _finish_job(job, str(exc))
        _set_progress(item, 100, 'Concluído', Item.Status.PROCESSED)
    except Exception as exc:
        # Relações são enriquecimento; não invalidam o conteúdo já processado.
        _fail_job(job, exc)
        _set_progress(
            item,
            100,
            'Concluído; relações não puderam ser analisadas',
            Item.Status.PROCESSED,
        )


def _process_extract_job(job: ProcessingJob) -> None:
    item = job.item
    _set_progress(item, 10, 'Lendo a fonte', Item.Status.PROCESSING)

    try:
        if item.type in {Item.Type.INSTAGRAM, Item.Type.YOUTUBE}:
            data = extract_video_metadata(item.source_url)
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
            source.metadata = data['metadata']
            source.save()

            item.save()
            _try_transcription(item)

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
            _set_progress(item, 100, 'Concluído', Item.Status.PROCESSED)

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
