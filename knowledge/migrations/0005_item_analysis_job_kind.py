from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0004_chunk_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='analysis',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='processingjob',
            name='kind',
            field=models.CharField(
                choices=[
                    ('extract', 'Extrair/processar fonte'),
                    ('analyze', 'Analisar com IA'),
                ],
                db_index=True,
                default='extract',
                max_length=20,
            ),
        ),
    ]
