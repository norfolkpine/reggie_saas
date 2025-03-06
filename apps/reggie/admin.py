from django.contrib import admin
from .models import KnowledgeBase, Agent, AgentInstruction, StorageBucket

@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ("name", "knowledge_type", "vector_table", "created_at", "last_updated")
    list_filter = ("knowledge_type", "created_at", "last_updated")
    search_fields = ("name", "vector_table")
    readonly_fields = ("created_at", "last_updated")  # Prevent manual editing of timestamps

    fieldsets = (
        ("General Information", {
            "fields": ("name", "knowledge_type", "path", "vector_table"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "last_updated"),
        }),
    )

@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "team", "is_global", "created_at")
    list_filter = ("is_global", "created_at")
    search_fields = ("name", "user__username")
    readonly_fields = ("created_at",)

@admin.register(AgentInstruction)
class AgentInstructionAdmin(admin.ModelAdmin):
    list_display = ("instruction", "agent", "category", "is_enabled", "created_at")
    list_filter = ("category", "is_enabled", "created_at")
    search_fields = ("instruction", "agent__name")
    readonly_fields = ("created_at",)

@admin.register(StorageBucket)
class StorageBucketAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "bucket_url")
    list_filter = ("provider",)
    search_fields = ("name", "bucket_url")