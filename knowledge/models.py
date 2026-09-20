from django.db import models
from django.urls import reverse


class Topic(models.Model):
    name = models.CharField(max_length=120, unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Project(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Item(models.Model):
    class Type(models.TextChoices):
        NOTE = 'note', 'Nota'
        INSTAGRAM = 'instagram', 'Instagram'
        YOUTUBE = 'youtube', 'YouTube'
        WEB = 'web', 'Página web'
        PDF = 'pdf', 'PDF'
        DOCUMENT = 'document', 'Documento'

    class Status(models.TextChoices):
        INBOX = 'inbox', 'Inbox'
        PROCESSING = 'processing', 'Processando'
        PROCESSED = 'processed', 'Processado'
        REVIEW = 'review', 'Para revisar'
        ERROR = 'error', 'Erro'
        ARCHIVED = 'archived', 'Arquivado'

    type = models.CharField(max_length=20, choices=Type.choices, default=Type.NOTE, db_index=True)
    title = models.CharField(max_length=300, blank=True)
    content = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    analysis = models.JSONField(default=dict, blank=True)
    processing_progress = models.PositiveSmallIntegerField(default=100)
    processing_stage = models.CharField(max_length=160, blank=True)
    source_url = models.URLField(max_length=2000, blank=True, db_index=True)
    source_author = models.CharField(max_length=200, blank=True)
    source_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INBOX, db_index=True)
    favorite = models.BooleanField(default=False, db_index=True)
    topics = models.ManyToManyField(Topic, blank=True, related_name='items')
    projects = models.ManyToManyField(Project, blank=True, related_name='items')
    tags = models.ManyToManyField(Tag, blank=True, related_name='items')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['type', 'status']),
            models.Index(fields=['favorite', '-updated_at']),
        ]

    def __str__(self):
        return self.title or f'{self.get_type_display()} #{self.pk}'

    def get_absolute_url(self):
        return reverse('item_detail', kwargs={'pk': self.pk})


class ItemSource(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name='source')
    platform = models.CharField(max_length=50, blank=True)
    caption = models.TextField(blank=True)
    description = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    original_hashtags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f'Fonte de {self.item}'


class Chunk(models.Model):
    class Kind(models.TextChoices):
        CONTENT = 'content', 'Conteúdo'
        CAPTION = 'caption', 'Legenda'
        TRANSCRIPT = 'transcript', 'Transcrição'
        PDF = 'pdf', 'PDF'

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='chunks')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CONTENT, db_index=True)
    text = models.TextField()
    position = models.PositiveIntegerField(default=0)
    page = models.PositiveIntegerField(null=True, blank=True)
    start_seconds = models.FloatField(null=True, blank=True)
    end_seconds = models.FloatField(null=True, blank=True)
    # V1 mantém JSON para rodar também em SQLite. O adaptador pgvector entra
    # no marco de busca semântica sem alterar a API do restante do sistema.
    embedding = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['item_id', 'kind', 'position']
        indexes = [
            models.Index(fields=['item', 'position']),
            models.Index(fields=['item', 'kind', 'position']),
        ]


class Relation(models.Model):
    class Origin(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        AI = 'ai', 'IA'
        SYSTEM = 'system', 'Sistema'

    class Status(models.TextChoices):
        SUGGESTED = 'suggested', 'Sugerida'
        CONFIRMED = 'confirmed', 'Confirmada'
        REJECTED = 'rejected', 'Rejeitada'

    class Type(models.TextChoices):
        RELATED = 'related', 'Relacionado'
        COMPLEMENTS = 'complements', 'Complementa'
        CONTRADICTS = 'contradicts', 'Contradiz'
        PART_OF = 'part_of', 'Parte de'
        USED_IN = 'used_in', 'Usado em'
        SAME_TOPIC = 'same_topic', 'Mesmo assunto'
        SAME_PROJECT = 'same_project', 'Mesmo projeto'
        CONTINUATION = 'continuation', 'Continuação'
        REFERENCE = 'reference', 'Referência'

    source = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='outgoing_relations')
    target = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='incoming_relations')
    relation_type = models.CharField(max_length=30, choices=Type.choices, default=Type.RELATED)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.MANUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    confidence = models.FloatField(null=True, blank=True)
    explanation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['source', 'target', 'relation_type'], name='unique_item_relation'),
            models.CheckConstraint(condition=~models.Q(source=models.F('target')), name='relation_not_self'),
        ]

    def __str__(self):
        return f'{self.source} → {self.target}'


class ProcessingJob(models.Model):
    class Kind(models.TextChoices):
        EXTRACT = 'extract', 'Extrair/processar fonte'
        ANALYZE = 'analyze', 'Analisar com IA'
        RELATE = 'relate', 'Descobrir relações'

    class State(models.TextChoices):
        PENDING = 'pending', 'Aguardando'
        RUNNING = 'running', 'Processando'
        DONE = 'done', 'Concluído'
        ERROR = 'error', 'Erro'

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='jobs')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.EXTRACT, db_index=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
