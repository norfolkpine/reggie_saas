from django.contrib import admin

from .models import (
    Agent,
    AgentExpectedOutput,
    AgentInstruction,
    AgentParameter,
    AgentUIProperties,
    Capability,
    Category,
    ChatSession,
    Document,
    DocumentTag,
    KnowledgeBase,
    ModelProvider,
    Project,
    StorageBucket,
    Tag,
    Website,
)

class AgentUIPropertiesInline(admin.StackedInline):
    model = AgentUIProperties
    extra = 0


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "team",
        "unique_code",
        "agent_id",
        "agent_knowledge_id",
        "is_global",
        "search_knowledge",
        "cite_knowledge",
        "created_at",
    )
    search_fields = ("name", "description")
    list_filter = (
        "is_global",
        "team",
        "search_knowledge",
        "show_tool_calls",
        "markdown_enabled",
    )
    filter_horizontal = ("subscriptions", "capabilities")
    readonly_fields = (
        "unique_code",
        "agent_id",
        "session_table",
        "memory_table",
        "agent_knowledge_id",
    )
    inlines = [AgentUIPropertiesInline]


@admin.register(AgentUIProperties)
class AgentUIPropertiesAdmin(admin.ModelAdmin):
    list_display = ("agent", "icon", "text_color", "background_color")
    search_fields = ("agent",)
    autocomplete_fields = ("agent",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(AgentInstruction)
class AgentInstructionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "short_instruction",
        "associated_agents",  # ✅ Replaces 'agent'
        "category",
        "is_enabled",
        "is_global",
        "is_system",
        "created_at",
    )
    search_fields = ("title", "instruction")
    list_filter = ("is_enabled", "is_global", "is_system", "category")
    autocomplete_fields = ("user",)

    def short_instruction(self, obj):
        return (obj.instruction[:75] + "...") if len(obj.instruction) > 75 else obj.instruction

    short_instruction.short_description = "Instruction"

    def associated_agents(self, obj):
        agents = obj.agents.all()  # uses related_name="agents" from Agent model
        return ", ".join(agent.name for agent in agents) if agents else "—"

    associated_agents.short_description = "Used By"


@admin.register(AgentExpectedOutput)
class AgentExpectedOutputAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "short_expected_output",
        "agent",
        "category",
        "is_enabled",
        "is_global",
        "created_at",
    )
    search_fields = (
        "title",
        "expected_output",
    )
    list_filter = ("is_enabled", "is_global", "category")
    autocomplete_fields = ("agent", "user")

    def short_expected_output(self, obj):
        return (obj.expected_output[:75] + "...") if len(obj.expected_output) > 75 else obj.expected_output

    short_expected_output.short_description = "Expected Output"


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
    list_display = ("agent", "key", "value")
    search_fields = ("key", "value")
    autocomplete_fields = ("agent",)


@admin.register(StorageBucket)
class StorageBucketAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "bucket_url")
    search_fields = ("name", "bucket_url")
    list_filter = ("provider",)


class AgentInline(admin.TabularInline):
    model = Agent
    fields = ("name", "user", "team", "is_global", "created_at")
    extra = 0
    readonly_fields = ("name", "user", "team", "is_global", "created_at")
    show_change_link = True


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ("name", "knowledge_type", "model_provider", "vector_table_name", "created_at", "updated_at")
    search_fields = ("name", "vector_table_name")
    list_filter = ("knowledge_type", "model_provider")
    autocomplete_fields = ("model_provider",)
    readonly_fields = (
        "unique_code",
        "knowledgebase_id",
        "vector_table_name",
    )
    inlines = [AgentInline]

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    search_fields = ("name", "description")
    autocomplete_fields = ("owner",)
    filter_horizontal = ("tags", "starred_by")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "file_path",
        "uploaded_by",
        "team",
        "visibility",
        "is_global",
        "source",
        "created_at",
        "updated_at",
    )
    search_fields = ("title", "description", "source")
    list_filter = ("visibility", "is_global", "tags")
    autocomplete_fields = ("team",)
    filter_horizontal = ("starred_by", "tags")
    readonly_fields = ("file_type",)

    def save_model(self, request, obj, form, change):
        """
        Automatically set 'uploaded_by' to the current admin user if not set.
        """
        if not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    def file_path(self, obj):
        return obj.file.url


@admin.register(DocumentTag)
class DocumentTagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


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


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id_display", "title", "agent", "user", "created_at", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")  # 👈 include 'id' here
    search_fields = ("id", "title")
    list_filter = ("agent", "user", "created_at")

    def session_id_display(self, obj):
        return str(obj.id)

    session_id_display.short_description = "Session ID"
