from django.contrib import admin
from .models import KnowledgeBase, KnowledgeBaseDocument

@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'vector_store_id', 'created_at', 'updated_at')
    search_fields = ('name', 'owner__username', 'vector_store_id')
    list_filter = ('created_at', 'owner')
    readonly_fields = ('vector_store_id', 'created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('name', 'owner')
        }),
        ('Storage Details', {
            'fields': ('vector_store_id',),
            'classes': ('collapse',), # Initially collapsed
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

@admin.register(KnowledgeBaseDocument)
class KnowledgeBaseDocumentAdmin(admin.ModelAdmin):
    list_display = ('knowledge_base', 'document', 'added_at')
    search_fields = ('knowledge_base__name', 'document__name')
    list_filter = ('added_at', 'knowledge_base')
    autocomplete_fields = ('knowledge_base', 'document') # Assuming DocAdmin has search_fields

    fieldsets = (
        (None, {
            'fields': ('knowledge_base', 'document')
        }),
        ('Timestamps', {
            'fields': ('added_at',),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('knowledge_base', 'document')
