from django.db import transaction
from .detector import detect_capture
from ..models import Item, ItemSource, ProcessingJob


def create_capture(raw: str, title: str = '') -> Item:
    detection = detect_capture(raw)
    kind_to_type = {
        'note': Item.Type.NOTE,
        'instagram': Item.Type.INSTAGRAM,
        'youtube': Item.Type.YOUTUBE,
        'web': Item.Type.WEB,
    }
    item_type = kind_to_type[detection.kind]

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
