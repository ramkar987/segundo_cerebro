import re

from django.db import migrations


def polish_existing_instagram_rows(apps, schema_editor):
    Item = apps.get_model('knowledge', 'Item')
    ItemSource = apps.get_model('knowledge', 'ItemSource')

    for item in Item.objects.filter(type='instagram').iterator():
        source = ItemSource.objects.filter(item_id=item.id).first()
        if not source:
            continue

        changed = []

        author = (item.source_author or '').strip()
        cleaned_author = re.sub(r'\s+\(@\d+\)$', '', author).strip()
        if cleaned_author != author:
            item.source_author = cleaned_author
            changed.append('source_author')

        caption = (source.caption or '').strip()
        if caption and (len(item.title or '') > 90 or (item.title or '').lower().startswith(('video by ', 'photo by '))):
            for line in caption.splitlines():
                candidate = ' '.join(line.split()).strip()
                if candidate and not candidate.startswith('#') and candidate != '.':
                    if len(candidate) > 82:
                        cut = candidate[:83].rsplit(' ', 1)[0].rstrip(' ,.;:-')
                        candidate = (cut or candidate[:82]).rstrip() + '…'
                    item.title = candidate
                    changed.append('title')
                    break

        if changed:
            item.save(update_fields=list(dict.fromkeys(changed)))


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0002_clean_instagram_rows'),
    ]

    operations = [
        migrations.RunPython(polish_existing_instagram_rows, migrations.RunPython.noop),
    ]
