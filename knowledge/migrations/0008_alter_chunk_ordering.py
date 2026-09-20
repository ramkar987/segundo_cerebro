from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0007_item_processing_progress'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='chunk',
            options={'ordering': ['item_id', 'kind', 'position']},
        ),
    ]
