from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0005_item_analysis_job_kind'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processingjob',
            name='kind',
            field=models.CharField(
                choices=[
                    ('extract', 'Extrair/processar fonte'),
                    ('analyze', 'Analisar com IA'),
                    ('relate', 'Descobrir relações'),
                ],
                db_index=True,
                default='extract',
                max_length=20,
            ),
        ),
    ]
