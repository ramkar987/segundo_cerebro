from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0003_polish_instagram_display'),
    ]

    operations = [
        migrations.AddField(
            model_name='chunk',
            name='kind',
            field=models.CharField(
                choices=[
                    ('content', 'Conteúdo'),
                    ('caption', 'Legenda'),
                    ('transcript', 'Transcrição'),
                    ('pdf', 'PDF'),
                ],
                db_index=True,
                default='content',
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name='chunk',
            index=models.Index(
                fields=['item', 'kind', 'position'],
                name='knowledge_c_item_id_54a9c4_idx',
            ),
        ),
    ]
