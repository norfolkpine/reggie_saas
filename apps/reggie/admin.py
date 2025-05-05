import logging

import requests
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.html import format_html

from apps.api.models import UserAPIKey

from .models import (
    Agent,
    AgentExpectedOutput,
    AgentInstruction,
    AgentParameter,
    AgentUIProperties,
    Capability,
    Category,
    ChatSession,
    File,
    FileKnowledgeBaseLink,
    FileTag,
    KnowledgeBase,
    ModelProvider,
    Project,
    StorageBucket,
    Tag,
    Website,
)

User = get_user_model()

logger = logging.getLogger(__name__)


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


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "file_link",  # ✅ Proper clickable link
        "uploaded_by",
        "team",
        "visibility",
        "is_global",
        "is_ingested",
        "gcs_path",
        "source",
        "created_at",
        "updated_at",
    )
    search_fields = ("title", "description", "source", "gcs_path")
    list_filter = ("visibility", "is_global", "tags", "is_ingested")
    autocomplete_fields = ("team",)
    filter_horizontal = ("starred_by", "tags")
    readonly_fields = ("file_type", "gcs_path", "is_ingested")

    actions = ["retry_ingestion"]  # ✅ Admin action to trigger ingestion manually

    def save_model(self, request, obj, form, change):
        """
        Automatically set 'uploaded_by' to the current admin user if not set.
        """
        if not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    def file_link(self, obj):
        """
        Returns a clickable file link for Admin panel.
        """
        if obj.file:
            return format_html('<a href="{}" target="_blank">View File</a>', obj.file.url)
        return "No file"

    file_link.short_description = "File"

    @admin.action(description="Retry ingestion of selected files")
    def retry_ingestion(self, request, queryset):
        """
        Admin bulk action to retry ingestion for selected files.
        """
        success = 0
        fail = 0
        skipped = 0

        # Get the system API key for Cloud Run
        try:
            logger.info("🔑 Looking up Cloud Run API key...")
            api_key_obj = UserAPIKey.objects.filter(
                name="Cloud Run Ingestion Service", user__email="cloud-run-service@system.local", revoked=False
            ).first()

            if not api_key_obj:
                self.message_user(
                    request,
                    "❌ No active Cloud Run API key found. Please run create_cloud_run_api_key management command.",
                    level="warning",
                )
                logger.warning("No active Cloud Run API key found")
            else:
                logger.info("✅ Found active Cloud Run API key")
                # Create new API key if needed
                api_key_obj, key = UserAPIKey.objects.create_key(
                    name="Cloud Run Ingestion Service", user=api_key_obj.user
                )

                # Test the API key with a simple request
                test_headers = {"Authorization": f"Api-Key {key}"}
                try:
                    test_url = f"{settings.LLAMAINDEX_INGESTION_URL}/"
                    logger.info(f"Testing API key with health check: {test_url}")
                    test_response = requests.get(test_url, headers=test_headers, timeout=5)
                    test_response.raise_for_status()
                    logger.info("✅ API key test successful")
                except Exception as e:
                    logger.error(f"❌ API key test failed: {str(e)}")
                    if hasattr(e, "response"):
                        logger.error(f"Response status: {e.response.status_code}")
                        logger.error(f"Response body: {e.response.text}")
                        logger.error(f"Request headers: {e.response.request.headers}")
        except Exception as e:
            logger.error(f"Failed to get Cloud Run API key: {e}")
            api_key_obj = None

        # Log settings for debugging
        logger.info(f"LLAMAINDEX_INGESTION_URL: {settings.LLAMAINDEX_INGESTION_URL}")

        for file_obj in queryset:
            # Skip if no gcs_path
            if not file_obj.gcs_path:
                self.message_user(request, f"❌ File {file_obj.id} has no GCS path. Skipping.", level="warning")
                fail += 1
                continue

            # Get all knowledge bases for this file
            kb_links = file_obj.knowledge_base_links.all()
            if not kb_links.exists():
                # Try team's default knowledge base
                if file_obj.team and hasattr(file_obj.team, "default_knowledge_base"):
                    kb = file_obj.team.default_knowledge_base
                    embedding_model = kb.model_provider.embedder_id if kb.model_provider else "text-embedding-ada-002"
                    chunk_size = kb.chunk_size or 1000
                    chunk_overlap = kb.chunk_overlap or 200
                else:
                    # Create a link to the default knowledge base
                    kb = KnowledgeBase.objects.filter(vector_table_name="pdf_documents").first()
                    if not kb:
                        self.message_user(
                            request, f"❌ No default knowledge base found for file {file_obj.id}.", level="error"
                        )
                        fail += 1
                        continue
                    embedding_model = "text-embedding-ada-002"
                    chunk_size = 1000
                    chunk_overlap = 200

                # Create a link
                link = FileKnowledgeBaseLink.objects.create(
                    file=file_obj,
                    knowledge_base=kb,
                    ingestion_status="processing",
                    embedding_model=embedding_model,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                kb_links = [link]

            # Process each knowledge base link
            for link in kb_links:
                try:
                    # Reset link status
                    link.ingestion_status = "processing"
                    link.ingestion_error = None
                    link.ingestion_progress = 0.0
                    link.processed_docs = 0
                    link.total_docs = 0
                    link.ingestion_started_at = timezone.now()
                    link.ingestion_completed_at = None
                    link.save()

                    # Call Cloud Run ingestion service
                    ingestion_url = f"{settings.LLAMAINDEX_INGESTION_URL}/ingest-file"
                    payload = {
                        "file_path": file_obj.storage_path,
                        "vector_table_name": link.knowledge_base.vector_table_name,
                        "file_uuid": str(file_obj.uuid),
                        "link_id": link.id,
                        "embedding_model": link.knowledge_base.model_provider.embedder_id
                        if link.knowledge_base.model_provider
                        else "text-embedding-ada-002",
                        "chunk_size": link.knowledge_base.chunk_size or 1000,
                        "chunk_overlap": link.knowledge_base.chunk_overlap or 200,
                    }
                    logger.info(
                        f"📤 Sending ingestion request for file {file_obj.id} to KB {link.knowledge_base.knowledgebase_id}"
                    )
                    logger.info(f"Payload: {payload}")

                    # Add API key to headers if available
                    headers = {"Content-Type": "application/json", "Accept": "application/json"}
                    if api_key_obj:
                        auth_header = f"Api-Key {key}"
                        headers["Authorization"] = auth_header
                        logger.info("✅ Using Cloud Run API key for authentication")
                    else:
                        logger.warning("No Cloud Run API key available for request")

                    logger.info(f"Request headers: {headers}")

                    try:
                        response = requests.post(
                            ingestion_url,
                            json=payload,
                            headers=headers,
                            timeout=30,  # 30 second timeout for the request itself
                        )
                        response.raise_for_status()

                        # Log response details
                        logger.info(f"Response status: {response.status_code}")
                        logger.info(f"Response headers: {response.headers}")
                        logger.info(f"Response body: {response.text}")

                        # The actual ingestion continues asynchronously, mark as ingested
                        file_obj.is_ingested = True
                        file_obj.save(update_fields=["is_ingested"])

                        success += 1
                        self.message_user(
                            request,
                            f"✅ Successfully queued ingestion for file {file_obj.id} into KB {link.knowledge_base.knowledgebase_id}",
                            level="success",
                        )
                    except requests.exceptions.RequestException as e:
                        # Log the error but don't fail the whole process
                        logger.error(f"Failed to queue ingestion for file {file_obj.id}: {e}")
                        if hasattr(e, "response"):
                            logger.error(f"Response status: {e.response.status_code}")
                            logger.error(f"Response headers: {e.response.headers}")
                            logger.error(f"Response body: {e.response.text}")
                            logger.error(f"Request headers: {e.response.request.headers}")

                        link.ingestion_status = "failed"
                        link.ingestion_error = str(e)
                        link.save()

                        self.message_user(
                            request,
                            f"❌ Failed to queue ingestion for file {file_obj.id} into KB {link.knowledge_base.knowledgebase_id}: {str(e)}",
                            level="error",
                        )
                        fail += 1

                except Exception as e:
                    logger.error(f"Unexpected error processing file {file_obj.id}: {e}")
                    link.ingestion_status = "failed"
                    link.ingestion_error = str(e)
                    link.save()
                    self.message_user(
                        request,
                        f"❌ Error processing file {file_obj.id} into KB {link.knowledge_base.knowledgebase_id}: {str(e)}",
                        level="error",
                    )
                    fail += 1

        self.message_user(
            request,
            f"✅ Retry complete: {success} queued, {fail} failed, {skipped} skipped.",
        )


@admin.register(FileTag)
class FileTagAdmin(admin.ModelAdmin):
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


@admin.register(FileKnowledgeBaseLink)
class FileKnowledgeBaseLinkAdmin(admin.ModelAdmin):
    list_display = (
        "file",
        "knowledge_base",
        "ingestion_status",
        "ingestion_progress",
        "processed_docs",
        "total_docs",
        "embedding_model",
        "created_at",
        "updated_at",
    )
    list_filter = ("ingestion_status", "knowledge_base", "embedding_model")
    search_fields = ("file__title", "knowledge_base__name", "embedding_model")
    readonly_fields = (
        "ingestion_progress",
        "processed_docs",
        "total_docs",
        "ingestion_started_at",
        "ingestion_completed_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-updated_at",)
    actions = ["reingest_selected"]

    @admin.action(description="Retry ingestion of selected file-knowledge base links")
    def reingest_selected(self, request, queryset):
        """
        Admin bulk action to retry ingestion for selected file-knowledge base links.
        """
        success = 0
        fail = 0

        # Get the system API key for Cloud Run
        try:
            logger.info("🔑 Looking up Cloud Run API key...")
            api_key_obj = UserAPIKey.objects.filter(
                name="Cloud Run Ingestion Service", user__email="cloud-run-service@system.local", revoked=False
            ).first()

            if not api_key_obj:
                self.message_user(
                    request,
                    "❌ No active Cloud Run API key found. Please run create_cloud_run_api_key management command.",
                    level="warning",
                )
                logger.warning("No active Cloud Run API key found")
                return
            else:
                logger.info("✅ Found active Cloud Run API key")
                # Create new API key if needed
                api_key_obj, key = UserAPIKey.objects.create_key(
                    name="Cloud Run Ingestion Service", user=api_key_obj.user
                )

                # Test the API key with a simple request
                test_headers = {"Authorization": f"Api-Key {key}"}
                try:
                    test_url = f"{settings.LLAMAINDEX_INGESTION_URL}/"
                    logger.info(f"Testing API key with health check: {test_url}")
                    test_response = requests.get(test_url, headers=test_headers, timeout=5)
                    test_response.raise_for_status()
                    logger.info("✅ API key test successful")
                except Exception as e:
                    logger.error(f"❌ API key test failed: {str(e)}")
                    if hasattr(e, "response"):
                        logger.error(f"Response status: {e.response.status_code}")
                        logger.error(f"Response body: {e.response.text}")
                        logger.error(f"Request headers: {e.response.request.headers}")
                    return
        except Exception as e:
            logger.error(f"Failed to get Cloud Run API key: {e}")
            self.message_user(request, f"❌ Failed to get Cloud Run API key: {str(e)}", level="error")
            return

        for link in queryset:
            try:
                # Reset status
                link.ingestion_status = "processing"
                link.ingestion_error = None
                link.ingestion_progress = 0.0
                link.processed_docs = 0
                link.total_docs = 0
                link.ingestion_started_at = timezone.now()
                link.ingestion_completed_at = None
                link.save()

                # Call Cloud Run ingestion service
                ingestion_url = f"{settings.LLAMAINDEX_INGESTION_URL}/ingest-file"
                headers = {"Authorization": f"Api-Key {key}", "Content-Type": "application/json"}
                response = requests.post(
                    ingestion_url,
                    json={
                        "file_path": link.file.storage_path,
                        "vector_table_name": link.knowledge_base.vector_table_name,
                        "file_uuid": str(link.file.uuid),
                        "link_id": link.id,
                        "embedding_model": link.knowledge_base.model_provider.embedder_id
                        if link.knowledge_base.model_provider
                        else "text-embedding-ada-002",
                        "chunk_size": link.knowledge_base.chunk_size or 1000,
                        "chunk_overlap": link.knowledge_base.chunk_overlap or 200,
                    },
                    headers=headers,
                    timeout=300,
                )
                response.raise_for_status()
                success += 1
                self.message_user(
                    request,
                    f"✅ Successfully queued reingestion for file {link.file.title} into KB {link.knowledge_base.name}",
                    level="success",
                )

            except Exception as e:
                fail += 1
                link.ingestion_status = "failed"
                link.ingestion_error = str(e)
                link.save(update_fields=["ingestion_status", "ingestion_error"])
                self.message_user(
                    request,
                    f"❌ Failed to reingest file {link.file.title} into KB {link.knowledge_base.name}: {str(e)}",
                    level="error",
                )

        self.message_user(
            request,
            f"✅ Reingestion complete: {success} queued successfully, {fail} failed.",
        )
