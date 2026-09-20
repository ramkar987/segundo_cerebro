from django.db import transaction

from .detector import detect_capture
from ..models import Item, ItemSource, ProcessingJob


def _existing_url_item(kind: str, normalized: str):
    exact = Item.objects.filter(source_url=normalized).first()
    if exact:
        return exact

    # Compatibilidade com capturas antigas do Instagram que ainda guardavam
    # ?stkn=... e outros parâmetros de compartilhamento.
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
            return existing

    with transaction.atomic():
        if item_type == Item.Type.NOTE:
            item = Item.objects.create(
                type=item_type,
                title=(title or detection.normalized[:80]).strip(),
                content=detection.normalized,
                status=Item.Status.PROCESSED,
            )
            ItemSource.objects.create(item=item, platform='manual')
        else:
            item = Item.objects.create(
                type=item_type,
                title=(title or 'Captura em processamento').strip(),
                source_url=detection.normalized,
                status=Item.Status.PROCESSING,
            )
            ItemSource.objects.create(item=item, platform=detection.kind)
            ProcessingJob.objects.create(item=item)
    return item
