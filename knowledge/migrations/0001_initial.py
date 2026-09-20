from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.TextField(blank=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Topic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='knowledge.topic')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('note', 'Nota'), ('instagram', 'Instagram'), ('youtube', 'YouTube'), ('web', 'Página web'), ('pdf', 'PDF'), ('document', 'Documento')], db_index=True, default='note', max_length=20)),
                ('title', models.CharField(blank=True, max_length=300)),
                ('content', models.TextField(blank=True)),
                ('summary', models.TextField(blank=True)),
                ('source_url', models.URLField(blank=True, db_index=True, max_length=2000)),
                ('source_author', models.CharField(blank=True, max_length=200)),
                ('source_date', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('inbox', 'Inbox'), ('processing', 'Processando'), ('processed', 'Processado'), ('review', 'Para revisar'), ('error', 'Erro'), ('archived', 'Arquivado')], db_index=True, default='inbox', max_length=20)),
                ('favorite', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('projects', models.ManyToManyField(blank=True, related_name='items', to='knowledge.project')),
                ('tags', models.ManyToManyField(blank=True, related_name='items', to='knowledge.tag')),
                ('topics', models.ManyToManyField(blank=True, related_name='items', to='knowledge.topic')),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='ItemSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform', models.CharField(blank=True, max_length=50)),
                ('caption', models.TextField(blank=True)),
                ('description', models.TextField(blank=True)),
                ('transcript', models.TextField(blank=True)),
                ('original_hashtags', models.JSONField(blank=True, default=list)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='source', to='knowledge.item')),
            ],
        ),
        migrations.CreateModel(
            name='Chunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField()),
                ('position', models.PositiveIntegerField(default=0)),
                ('page', models.PositiveIntegerField(blank=True, null=True)),
                ('start_seconds', models.FloatField(blank=True, null=True)),
                ('end_seconds', models.FloatField(blank=True, null=True)),
                ('embedding', models.JSONField(blank=True, default=list)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='knowledge.item')),
            ],
            options={'ordering': ['item_id', 'position']},
        ),
        migrations.CreateModel(
            name='ProcessingJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.CharField(choices=[('pending', 'Aguardando'), ('running', 'Processando'), ('done', 'Concluído'), ('error', 'Erro')], db_index=True, default='pending', max_length=20)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='jobs', to='knowledge.item')),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.CreateModel(
            name='Relation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('relation_type', models.CharField(choices=[('related', 'Relacionado'), ('complements', 'Complementa'), ('contradicts', 'Contradiz'), ('part_of', 'Parte de'), ('used_in', 'Usado em'), ('same_topic', 'Mesmo assunto'), ('same_project', 'Mesmo projeto'), ('continuation', 'Continuação'), ('reference', 'Referência')], default='related', max_length=30)),
                ('origin', models.CharField(choices=[('manual', 'Manual'), ('ai', 'IA'), ('system', 'Sistema')], default='manual', max_length=20)),
                ('status', models.CharField(choices=[('suggested', 'Sugerida'), ('confirmed', 'Confirmada'), ('rejected', 'Rejeitada')], default='confirmed', max_length=20)),
                ('confidence', models.FloatField(blank=True, null=True)),
                ('explanation', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='outgoing_relations', to='knowledge.item')),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_relations', to='knowledge.item')),
            ],
        ),
        migrations.AddIndex(model_name='item', index=models.Index(fields=['type', 'status'], name='knowledge_i_type_784a20_idx')),
        migrations.AddIndex(model_name='item', index=models.Index(fields=['favorite', '-updated_at'], name='knowledge_i_favorit_2cdd1c_idx')),
        migrations.AddIndex(model_name='chunk', index=models.Index(fields=['item', 'position'], name='knowledge_c_item_id_785e79_idx')),
        migrations.AddConstraint(model_name='relation', constraint=models.UniqueConstraint(fields=('source', 'target', 'relation_type'), name='unique_item_relation')),
        migrations.AddConstraint(model_name='relation', constraint=models.CheckConstraint(condition=~models.Q(source=models.F('target')), name='relation_not_self')),
    ]
