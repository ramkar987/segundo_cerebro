from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Item, ProcessingJob
from .extractors import extract_video_metadata, extract_webpage
from .transcription import (
    TranscriptionSkipped,
    mark_transcription_state,
    transcribe_item,
)


def claim_next_job():
    with transaction.atomic():
        job = (ProcessingJob.objects.select_for_update(skip_locked=True)
               .filter(state=ProcessingJob.State.PENDING)
               .order_by('created_at')
               .first())
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
        return

    try:
        transcribe_item(item)
    except TranscriptionSkipped as exc:
        mark_transcription_state(item, 'skipped', str(exc))
    except Exception as exc:
        # Metadados/legenda continuam válidos mesmo que o provedor de
        # transcrição esteja indisponível. Registramos o erro para nova tentativa.
        mark_transcription_state(item, 'error', str(exc))


def process_job(job: ProcessingJob):
    item = job.item
    try:
        if item.type in {Item.Type.INSTAGRAM, Item.Type.YOUTUBE}:
            data = extract_video_metadata(item.source_url)

            if item.type == Item.Type.INSTAGRAM:
                item.title = _useful_instagram_title(data['title'], data['caption'])
                # A legenda vive em ItemSource.caption. Não duplicamos no campo
                # genérico content; a busca inclui a fonte separadamente.
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

            _try_transcription(item)

        elif item.type == Item.Type.WEB:
            data = extract_webpage(item.source_url, timeout=settings.WEB_FETCH_TIMEOUT)
            item.title = data['title'] or item.title
            item.content = data['content']
        else:
            raise ValueError(f'Tipo não processável: {item.type}')

        item.status = Item.Status.PROCESSED
        item.save()
        job.state = ProcessingJob.State.DONE
        job.finished_at = timezone.now()
        job.error = ''
        job.save(update_fields=['state', 'finished_at', 'error'])

    except Exception as exc:
        item.status = Item.Status.ERROR
        item.save(update_fields=['status', 'updated_at'])
        job.state = ProcessingJob.State.ERROR
        job.finished_at = timezone.now()
        job.error = str(exc)[:5000]
        job.save(update_fields=['state', 'finished_at', 'error'])
        raise
