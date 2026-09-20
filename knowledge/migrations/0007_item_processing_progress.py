from django.db import migrations, models


def initialize_progress(apps, schema_editor):
    Item = apps.get_model('knowledge', 'Item')
    Item.objects.filter(status='processing').update(
        processing_progress=5,
        processing_stage='Na fila',
    )
    Item.objects.exclude(status='processing').update(
        processing_progress=100,
        processing_stage='Concluído',
    )


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0006_processingjob_relate'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='processing_progress',
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name='item',
            name='processing_stage',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.RunPython(initialize_progress, migrations.RunPython.noop),
    ]
