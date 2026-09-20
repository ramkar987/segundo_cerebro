from django.contrib import admin
from .models import Chunk, Item, ItemSource, ProcessingJob, Project, Relation, Tag, Topic

class ItemSourceInline(admin.StackedInline):
    model = ItemSource
    extra = 0

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'status', 'favorite', 'source_author', 'updated_at')
    list_filter = ('type', 'status', 'favorite')
    search_fields = ('title', 'content', 'summary', 'source_author', 'source_url')
    filter_horizontal = ('tags', 'topics', 'projects')
    inlines = [ItemSourceInline]

@admin.register(Relation)
class RelationAdmin(admin.ModelAdmin):
    list_display = ('source', 'relation_type', 'target', 'origin', 'status', 'confidence')
    list_filter = ('relation_type', 'origin', 'status')

admin.site.register([Chunk, ProcessingJob, Project, Tag, Topic])
