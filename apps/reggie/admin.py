from django.contrib import admin
from .models import (
    Agent,
    AgentInstruction,
    AgentExpectedOutput,
    AgentParameter,
    StorageBucket,
    KnowledgeBase,
    Tag,
    Project,
    Document,
    DocumentTag,
    Website,
    ModelProvider
)


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'team', 'is_global', 'search_knowledge', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('is_global', 'team', 'search_knowledge', 'show_tool_calls', 'markdown_enabled')
    filter_horizontal = ('subscriptions',)


@admin.register(AgentInstruction)
class AgentInstructionAdmin(admin.ModelAdmin):
    list_display = ('instruction', 'agent', 'category', 'is_enabled', 'is_global', 'created_at')
    search_fields = ('instruction',)
    list_filter = ('is_enabled', 'is_global', 'category')
    autocomplete_fields = ('agent', 'user')

@admin.register(AgentExpectedOutput)
class AgentInstructionAdmin(admin.ModelAdmin):
    list_display = ('output', 'agent', 'category', 'is_enabled', 'is_global', 'created_at')
    search_fields = ('output',)
    list_filter = ('is_enabled', 'is_global', 'category')
    autocomplete_fields = ('agent', 'user')

@admin.register(ModelProvider)
class ModelProviderAdmin(admin.ModelAdmin):
    list_display = ("provider", "model_name", "is_enabled")
    list_filter = ("provider", "is_enabled")
    search_fields = ("model_name",)
    actions = ["enable_models", "disable_models"]

    def enable_models(self, request, queryset):
        queryset.update(is_enabled=True)
    enable_models.short_description = "Enable selected models"

    def disable_models(self, request, queryset):
        queryset.update(is_enabled=False)
    disable_models.short_description = "Disable selected models"


@admin.register(AgentParameter)
class AgentParameterAdmin(admin.ModelAdmin):
    list_display = ('agent', 'key', 'value')
    search_fields = ('key', 'value')
    autocomplete_fields = ('agent',)


@admin.register(StorageBucket)
class StorageBucketAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'bucket_url')
    search_fields = ('name', 'bucket_url')
    list_filter = ('provider',)


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'knowledge_type', 'vector_table_name', 'created_at', 'updated_at')
    search_fields = ('name', 'vector_table_name')
    list_filter = ('knowledge_type',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner')
    search_fields = ('name', 'description')
    autocomplete_fields = ('owner',)
    filter_horizontal = ('tags', 'starred_by')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'uploaded_by', 'team', 'visibility', 'is_global', 'source', 'created_at', 'updated_at')
    search_fields = ('title', 'description', 'source')
    list_filter = ('visibility', 'is_global', 'tags')
    autocomplete_fields = ('team',)
    filter_horizontal = ('starred_by', 'tags')

    def save_model(self, request, obj, form, change):
        """
        Automatically set 'uploaded_by' to the current admin user if not set.
        """
        if not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DocumentTag)
class DocumentTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = (
        "url",
        "name",
        "owner",
        "is_active",
        "crawl_status",
        "last_crawled",
        "created_at",
    )
    list_filter = ("is_active", "crawl_status", "tags")
    search_fields = ("url", "name", "description")
    readonly_fields = ("owner", "created_at", "updated_at", "last_crawled")
    ordering = ("-created_at",)

    def save_model(self, request, obj, form, change):
        """Auto-assign the owner to the logged-in user when creating a new Website."""
        if not change:  # Only set owner on creation
            obj.owner = request.user
        super().save_model(request, obj, form, change)
