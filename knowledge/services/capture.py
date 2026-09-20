from django.conf import settings
from django.db import transaction

from .detector import detect_capture
from ..models import Item, ItemSource, ProcessingJob


class DuplicateCapture(Exception):
    def __init__(self, item: Item):
        self.item = item
        super().__init__('Este conteúdo já foi guardado.')


def _existing_url_item(kind: str, normalized: str):
    exact = Item.objects.filter(source_url=normalized).first()
    if exact:
        return exact

    # Compatibilidade com capturas antigas do Instagram que ainda guardavam
    # parâmetros de compartilhamento.
    if kind == 'instagram':
        return Item.objects.filter(source_url__startswith=normalized).first()

    return None


def create_capture(raw: str, title: str = '') -> Item:
    detection = detect_capture(raw)
    kind_to_type = {
        'note': Item.Type.NOTE,
        'instagram': Item.Type.INSTAGRAM,
        'youtube': Item.Type.YOUTUBE,
        'web': Item.Type.WEB,
    }
    item_type = kind_to_type[detection.kind]

    if item_type != Item.Type.NOTE:
        existing = _existing_url_item(detection.kind, detection.normalized)
        if existing:
            raise DuplicateCapture(existing)

    with transaction.atomic():
        if item_type == Item.Type.NOTE:
            should_analyze = bool(settings.ANALYZE_CONTENT and settings.GROQ_API_KEY)
            item = Item.objects.create(
                type=item_type,
                title=(title or detection.normalized[:80]).strip(),
                content=detection.normalized,
                status=Item.Status.PROCESSING if should_analyze else Item.Status.PROCESSED,
                processing_progress=70 if should_analyze else 100,
                processing_stage='Aguardando análise da IA' if should_analyze else 'Concluído',
            )
            ItemSource.objects.create(item=item, platform='manual')
            if should_analyze:
                ProcessingJob.objects.create(item=item, kind=ProcessingJob.Kind.ANALYZE)
        else:
            item = Item.objects.create(
                type=item_type,
                title=(title or 'Captura em processamento').strip(),
                source_url=detection.normalized,
                status=Item.Status.PROCESSING,
                processing_progress=5,
                processing_stage='Na fila',
            )
            ItemSource.objects.create(item=item, platform=detection.kind)
            ProcessingJob.objects.create(item=item, kind=ProcessingJob.Kind.EXTRACT)
    return item
