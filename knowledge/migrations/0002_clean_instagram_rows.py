from django.db import migrations


def clean_instagram_rows(apps, schema_editor):
    Item = apps.get_model('knowledge', 'Item')
    ItemSource = apps.get_model('knowledge', 'ItemSource')

    for item in Item.objects.filter(type='instagram').iterator():
        source = ItemSource.objects.filter(item_id=item.id).first()
        if not source:
            continue

        changed = []

        if item.content and source.caption and item.content.strip() == source.caption.strip():
            item.content = ''
            changed.append('content')

        title = (item.title or '').strip()
        if title.lower().startswith(('video by ', 'photo by ')) and source.caption:
            for line in source.caption.splitlines():
                candidate = ' '.join(line.split()).strip()
                if candidate and not candidate.startswith('#') and candidate != '.':
                    item.title = candidate[:120]
                    changed.append('title')
                    break

        metadata = source.metadata or {}
        handle = (metadata.get('uploader_id') or '').strip().lstrip('@')
        author = (item.source_author or '').strip()
        if handle and author and handle.lower() not in author.lower():
            item.source_author = f'{author} (@{handle})'
            changed.append('source_author')
        elif handle and not author:
            item.source_author = f'@{handle}'
            changed.append('source_author')

        # Remove parâmetros de compartilhamento antigos do Instagram.
        if item.source_url:
            base = item.source_url.split('?', 1)[0].split('#', 1)[0]
            if not base.endswith('/'):
                base += '/'
            if base != item.source_url:
                item.source_url = base
                changed.append('source_url')

        if changed:
            item.save(update_fields=list(dict.fromkeys(changed)))


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(clean_instagram_rows, migrations.RunPython.noop),
    ]
