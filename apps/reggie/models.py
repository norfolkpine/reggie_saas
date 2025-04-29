import os
import re
import uuid
from datetime import datetime

from agno.knowledge import AgentKnowledge
from agno.vectordb.pgvector import PgVector

# import psycopg2
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.signing import Signer
from django.db import models
from django.utils.text import slugify

from apps.reggie.utils.gcs_utils import ingest_single_file
from apps.teams.models import (
    BaseTeamModel,  # Adding a model for Teams specific projects. This will be a future improvement
)
from apps.users.models import CustomUser
from apps.utils.models import BaseModel


def generate_unique_code():
    return uuid.uuid4().hex[:12]


def generate_full_uuid():
    # use .hex to returns a 32-character hex string (no hyphens)
    return uuid.uuid4()


# Making changes so the session table can use a unique agent name
def generate_agent_id(provider: str, name: str) -> str:
    prefix = provider[0].lower() if provider else "x"
    short_code = uuid.uuid4().hex[:9]
    slug = slugify(name)[:10]
    agent_id = f"{prefix}-{short_code}-{slug}"
    return agent_id.rstrip("-")


def generate_knowledgebase_id(provider: str, name: str) -> str:
    prefix = f"kb{provider[0].lower()}" if provider else "kbx"
    short_code = uuid.uuid4().hex[:6]
    slug = slugify(name)[:12]
    kb_id = f"{prefix}-{short_code}-{slug}"
    return kb_id.rstrip("-")


def clean_table_name(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    full = base.rstrip("_")  # Remove trailing underscores
    return full[:40]


class Agent(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agents")
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)

    category = models.ForeignKey("Category", on_delete=models.CASCADE, related_name="agents", null=True, blank=True)

    capabilities = models.ManyToManyField("Capability", related_name="agents", blank=True)

    agent_id = models.CharField(
        max_length=64,
        unique=False,
        editable=False,
        blank=True,
        help_text="Unique identifier for the agent, used for session storage.",
    )

    unique_code = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_full_uuid,
        help_text="Unique identifier for the agent, used for session storage.",
    )

    memory_table = models.CharField(
        max_length=255,
        editable=False,
        unique=True,
        blank=True,
        help_text="Table name for memory persistence, unique to this agent.",
    )

    session_table = models.CharField(
        max_length=255,
        editable=False,
        unique=True,
        blank=True,
        help_text="Table name for session persistence, derived from unique_code.",
    )

    # Not really needed for RBAC, will keep in case we generate a unique table
    agent_knowledge_id = models.CharField(
        max_length=255,
        editable=False,
        unique=True,
        blank=True,
        null=True,  # <-- this allows NULLs (which are unique in PostgreSQL)
        help_text="Table name for knowledge base persistence, derived from unique_code.",
    )

    model = models.ForeignKey(
        "ModelProvider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
        help_text="AI model used by the agent.",
    )
    instructions = models.ForeignKey(
        "AgentInstruction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
        help_text="The predefined instructions assigned to this agent.",
    )

    expected_output = models.ForeignKey(
        "AgentExpectedOutput",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
        help_text="The predefined expected output template assigned to this agent.",
    )
    # Used for Knowledge base table in agent builder
    knowledge_base = models.ForeignKey("KnowledgeBase", on_delete=models.CASCADE, null=True, blank=True)

    search_knowledge = models.BooleanField(default=True)
    cite_knowledge = models.BooleanField(default=True)
    read_chat_history = models.BooleanField(default=True)
    add_datetime_to_instructions = models.BooleanField(default=True)
    show_tool_calls = models.BooleanField(default=False)
    read_tool_call_history = models.BooleanField(default=True)
    markdown_enabled = models.BooleanField(default=True)
    debug_mode = models.BooleanField(default=False, help_text="Enable debug mode for logging.")
    num_history_responses = models.IntegerField(default=3, help_text="Number of past responses to keep in chat memory.")
    add_history_to_messages = models.BooleanField(default=True)

    is_global = models.BooleanField(default=False)

    subscriptions = models.ManyToManyField("djstripe.Subscription", related_name="agents", blank=True)

    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, null=True, blank=True, related_name="agents")

    def save(self, *args, **kwargs):
        creating = not self.pk

        if creating:
            # Generate unique code
            self.unique_code = generate_full_uuid()

            # Ensure model and name exist before generating agent_id
            provider_name = self.model.provider if self.model else "x"
            self.agent_id = generate_agent_id(provider_name, self.name)
            clean_id = clean_table_name(self.agent_id)

            # Use agent_id in session and knowledge table names
            self.session_table = f"agent_session_{clean_id}"
            self.agent_knowledge_id = f"agent_kb_{clean_id}"  # knowledge_table

            # Optionally: you can use agent_id here too for consistency
            self.memory_table = f"agent_memory_{clean_id}"

        else:
            # Lock down identity fields after creation
            orig = Agent.objects.get(pk=self.pk)
            self.unique_code = orig.unique_code
            self.agent_id = orig.agent_id
            self.session_table = orig.session_table
            self.agent_knowledge_id = orig.agent_knowledge_id  # knowledge_table
            self.memory_table = orig.memory_table

        super().save(*args, **kwargs)

    def clean(self):
        super().clean()

        if self.knowledge_base and self.knowledge_base.model_provider:
            kb_provider = self.knowledge_base.model_provider.provider
            agent_provider = self.model.provider if self.model else None

            if kb_provider != agent_provider:
                raise ValidationError(
                    {
                        "knowledge_base": f"Selected knowledge base uses provider '{kb_provider}', "
                        f"but this agent is configured for '{agent_provider}'."
                    }
                )

    def __str__(self):
        return self.name

    def is_accessible_by_user(self, user):
        if self.is_global:
            return True
        if user.is_superuser:
            return True
        if self.team and self.team.members.filter(id=user.id).exists():
            return True
        if self.subscriptions.filter(customer__user=user, status="active").exists():
            return True
        return False

    # Used by AgentBuilder, users should not see system instructions
    def get_active_instructions(self):
        """
        Returns all enabled instructions relevant to this agent:
        - The one directly assigned (if any)
        - All system-level instructions (is_system=True)
        """
        system_qs = AgentInstruction.objects.filter(is_system=True, is_enabled=True)

        if self.instructions and self.instructions.is_enabled:
            return system_qs.union(AgentInstruction.objects.filter(pk=self.instructions.pk))

        return system_qs

    def get_active_outputs(self):
        return AgentExpectedOutput.objects.filter(models.Q(agent=self) | models.Q(is_global=True), is_enabled=True)


class AgentUIProperties(BaseModel):
    agent = models.OneToOneField(Agent, on_delete=models.CASCADE, related_name="ui_properties")
    icon = models.CharField(max_length=255, blank=True, null=True)
    text_color = models.CharField(max_length=255, blank=True, null=True)
    background_color = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.agent.name} - {self.icon}"


class Category(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Capability(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Capabilities"


class ModelProvider(BaseModel):
    PROVIDERS = [
        ("openai", "OpenAI"),
        ("google", "Google"),
        ("anthropic", "Anthropic"),
        ("groq", "Groq"),
    ]

    provider = models.CharField(
        max_length=20, choices=PROVIDERS, help_text="LLM provider (e.g., OpenAI, Google, Anthropic, Groq)."
    )
    model_name = models.CharField(
        max_length=50, unique=True, help_text="Model identifier (e.g., gpt-4o, gemini-pro, claude-3)."
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the model, its strengths, or use case (e.g., best for summarization).",
    )
    embedder_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ID of the embedder model (e.g., 'text-embedding-ada-002', 'text-embedding-004')",
    )

    embedder_dimensions = models.IntegerField(
        blank=True, null=True, help_text="Vector size of the embedder (e.g., 1536, 768)"
    )

    is_enabled = models.BooleanField(default=True, help_text="Whether this model is available for use.")

    def __str__(self):
        status = "✅ Enabled" if self.is_enabled else "❌ Disabled"
        return f"{self.get_provider_display()} - {self.model_name} ({status})"


# Not using
class AgentParameter(BaseModel):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="parameters")
    key = models.CharField(max_length=255)  # Parameter name
    value = models.TextField()  # Can store different types of values (string, number, etc.)

    class Meta:
        unique_together = ("agent", "key")  # Ensure no duplicate keys for an agent

    def __str__(self):
        return f"{self.agent.name} - {self.key}: {self.value}"


# Agent Instructions
class InstructionCategory(models.TextChoices):
    SCOPE = "Scope & Knowledge Boundaries", "Scope & Knowledge Boundaries"
    RETRIEVAL = "Information Retrieval & Accuracy", "Information Retrieval & Accuracy"
    RESPONSE_FORMATTING = "Response Handling & Formatting", "Response Handling & Formatting"
    COMPLIANCE = "Compliance-Specific Instructions", "Compliance-Specific Instructions"
    PERSONALITY = "Personality", "Personality"
    PROCESS = "Process", "Process"
    IMPROVEMENT = "Improvement", "Improvement"
    TEMPLATE = "Template", "Template"
    USER = "User", "User-Defined Primary Instruction"
    SYSTEM = "System", "System-Level Instruction"


class AgentInstruction(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="instructions")
    # agent = models.ForeignKey(
    #     "Agent",
    #     on_delete=models.CASCADE,
    #     related_name="instructions",
    #     null=True,  # Allows null if the instruction is global
    #     blank=True
    # )
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional title for the instruction, e.g., 'Default Retrieval Strategy'.",
    )
    instruction = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=InstructionCategory.choices,
        default=InstructionCategory.TEMPLATE,
    )

    is_template = models.BooleanField(default=True)
    is_enabled = models.BooleanField(default=True)
    is_global = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False, help_text="Flag for platform/system-level instructions.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "✅ Enabled" if self.is_enabled else "❌ Disabled"
        scope = "🌍 Global" if self.is_global else "🔹 Agent: N/A"
        label = self.title or self.instruction[:50]
        return f"[{self.get_category_display()}] {label}... ({scope}, {status})"


# Expected Output
# expected_output
class AgentExpectedOutput(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="outputs")
    agent = models.ForeignKey(
        "Agent",
        on_delete=models.CASCADE,
        related_name="outputs",
        null=True,  # Allows null if the instruction is global
        blank=True,
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional title for this expected output, e.g., 'Basic Research Report'.",
    )
    expected_output = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=InstructionCategory.choices,
        default=InstructionCategory.RESPONSE_FORMATTING,
    )

    is_enabled = models.BooleanField(default=True)  # Allows enabling/disabling instructions
    is_global = models.BooleanField(default=False)  # New: Makes the instruction available to all agents
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "✅ Enabled" if self.is_enabled else "❌ Disabled"
        scope = "🌍 Global" if self.is_global else f"🔹 Agent: {self.agent.name if self.agent else 'N/A'}"
        return f"[{self.get_category_display()}] {self.title}, {self.expected_output[:50]}... ({scope}, {status})"


# Storage Buckets
class StorageProvider(models.TextChoices):
    LOCAL = "local", "Local Storage"
    AWS_S3 = "aws_s3", "Amazon S3"
    GCS = "gcs", "Google Cloud Storage"


class StorageBucket(BaseModel):
    name = models.CharField(max_length=255, unique=True, help_text="Name of the storage bucket (e.g., 'Main Tax Docs')")
    provider = models.CharField(
        max_length=10,
        choices=StorageProvider.choices,
        default=StorageProvider.LOCAL,
        help_text="Storage provider (Local, AWS S3, or Google Cloud Storage).",
    )
    bucket_url = models.CharField(
        max_length=500,
        unique=True,
        help_text="Full storage bucket URL (e.g., 's3://my-bucket/', 'gcs://my-bucket/', or local path)",
    )

    def __str__(self):
        return f"{self.name} ({self.get_provider_display()})"


# Knowledge bases
# https://docs.phidata.com/knowledge/introduction


# Kind of useless for now, we will only use the one knowledgebase. Might use Langchain vector to easily combine
# https://github.com/agno-agi/agno/blob/main/cookbook/agent_concepts/knowledge/llamaindex_kb.py
class KnowledgeBaseType(models.TextChoices):
    AGNO_PGVECTOR = "agno_pgvector", "Agno PGVector (default)"
    LLAMAINDEX = "llamaindex", "LlamaIndex VectorStore"
    ARXIV = "arxiv", "ArXiv Papers"
    COMBINED = "combined", "Combined Knowledge Base"
    CSV = "csv", "CSV Files"
    DOCUMENT = "document", "Document Files (DOCX)"
    JSON = "json", "JSON Files"
    LANGCHAIN = "langchain", "LangChain Retriever"
    PDF = "pdf", "Local PDF Files"
    PDF_URL = "pdf_url", "PDF Files from URLs"
    S3_PDF = "s3_pdf", "PDF Files from S3"
    S3_TEXT = "s3_text", "Text Files from S3"
    TEXT = "text", "Local Text Files"
    WEBSITE = "website", "Website Data"
    WIKIPEDIA = "wikipedia", "Wikipedia Articles"
    OTHER = "other", "Other Knowledge Type"


class KnowledgeBase(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)

    knowledge_type = models.CharField(
        max_length=20,
        choices=KnowledgeBaseType.choices,
        default=KnowledgeBaseType.LLAMAINDEX,
        help_text="Defines how this knowledge base is structured (e.g., PDFs, SQL, API, etc.).",
    )

    model_provider = models.ForeignKey(
        "ModelProvider",
        on_delete=models.SET_NULL,
        null=True,
        # blank=True,
        help_text="LLM provider to use for embeddings in this knowledge base.",
    )

    path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Path for files or storage location (e.g., local dir, URL, S3 bucket).",
    )

    unique_code = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_full_uuid,
        help_text="Globally unique identifier for the knowledge base.",
    )

    # Used for Metadata inside of shared knowledgebase table. Use RBAC.
    knowledgebase_id = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        blank=True,
        help_text="Unique slugified identifier used for referencing and table naming.",
    )

    vector_table_name = models.CharField(
        max_length=255,
        unique=True,
        editable=False,
        blank=True,
        help_text="Postgres vector table name used for embeddings.",
    )

    ## Add Subscriptions
    # subscriptions = models.ManyToManyField("djstripe.Subscription", related_name="knowledge_bases", blank=True)
    # team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, null=True, blank=True, related_name="knowledge_bases")

    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp when the knowledge base was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when the knowledge base was last updated.")

    def save(self, *args, **kwargs):
        creating = not self.pk

        if creating:
            self.unique_code = generate_full_uuid()
            # Ensure model and name exist before generating agent_id
            provider_name = self.model_provider.provider if self.model_provider else "x"
            self.knowledgebase_id = generate_knowledgebase_id(provider_name, self.name)
            clean_id = clean_table_name(self.knowledgebase_id)
            self.vector_table_name = clean_id

        else:
            original = KnowledgeBase.objects.get(pk=self.pk)
            self.unique_code = original.unique_code
            self.knowledgebase_id = original.knowledgebase_id
            self.vector_table_name = original.vector_table_name

        super().save(*args, **kwargs)
        if creating:
            try:
                self.build_knowledge().vector_db.create()
            except Exception as e:
                print(f"❌ Failed to create vector table: {e}")

    def get_embedder(self):
        if not self.model_provider or not self.model_provider.embedder_id:
            raise ValueError("Embedder configuration is missing for this knowledge base.")

        provider = self.model_provider.provider
        embedder_id = self.model_provider.embedder_id
        dimensions = self.model_provider.embedder_dimensions or 1536

        if provider == "openai":
            from agno.embedder.openai import OpenAIEmbedder

            return OpenAIEmbedder(id=embedder_id, dimensions=dimensions)
        elif provider == "google":
            from agno.embedder.google import GeminiEmbedder

            return GeminiEmbedder(id=embedder_id, dimensions=dimensions)
        elif provider == "anthropic":
            from agno.embedder.anthropic import ClaudeEmbedder

            return ClaudeEmbedder(id=embedder_id, dimensions=dimensions)
        elif provider == "groq":
            from agno.embedder.groq import GroqEmbedder

            return GroqEmbedder(id=embedder_id, dimensions=dimensions)

        raise ValueError(f"Unsupported provider: {provider}")

    def build_knowledge(self) -> AgentKnowledge:
        return AgentKnowledge(
            vector_db=PgVector(
                db_url=settings.DATABASE_URL,
                table_name=self.vector_table_name,
                # schema="ai",
                embedder=self.get_embedder(),
            ),
            num_documents=3,
        )

    def __str__(self):
        return f"{self.name}({self.model_provider.provider}, {self.get_knowledge_type_display()})"


## Projects
# Tag model for flexible categorization
class Tag(BaseModel):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


# Project model for grouping chats
class Project(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    # created_at = models.DateTimeField(auto_now_add=True)
    # updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="owned_projects")
    # Add shared team access to projects
    # members = models.ManyToManyField(CustomUser, related_name='projects', blank=True)
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="projects",
        null=True,
        blank=True,
        help_text="Team this project belongs to (optional if personal).",
    )
    tags = models.ManyToManyField(Tag, blank=True)
    starred_by = models.ManyToManyField(CustomUser, related_name="starred_projects", blank=True)

    def __str__(self):
        return self.name


class TeamProject(BaseTeamModel):  # ✅ Inherits from BaseTeamModel to get `team` field
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True)
    starred_by = models.ManyToManyField(CustomUser, related_name="starred_team_projects", blank=True)

    def __str__(self):
        return self.name


## Chat sessions
class ChatSession(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="chat_sessions")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=255, default="New Chat")

    def __str__(self):
        return f"{self.title} ({self.agent.name})"

    class Meta:
        ordering = ["-updated_at"]


#######################


## File Models (not used)
def user_document_path(instance, filename):
    """
    Generates path for file uploads to GCS, organized by user and date.
    Example: documents/45/2025/03/11/filename.pdf
    """
    user_id = instance.uploaded_by.id if instance.uploaded_by else "anonymous"
    today = datetime.today()
    return f"document/{user_id}/{today.year}/{today.month:02d}/{today.day:02d}/{filename}"


## File Models (previously documents)
def user_file_path(instance, filename):
    """
    Determines GCS path for file uploads:
    - Global files go into 'global/library/{date}/filename'.
    - User-specific files go into 'user_files/{user_id}-{user_uuid}/{date}/filename'.
    """
    today = datetime.today()

    if getattr(instance, "is_global", False):
        return f"global/library/{today.year}/{today.month:02d}/{today.day:02d}/{filename}"
    else:
        if instance.uploaded_by:
            user_id = instance.uploaded_by.id
            user_uuid = instance.uploaded_by.uuid
            user_folder = f"{user_id}-{user_uuid}"
        else:
            user_folder = "anonymous"

        return f"user_files/{user_folder}/{today.year}/{today.month:02d}/{today.day:02d}/{filename}"


class FileTag(BaseModel):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class FileType(models.TextChoices):
    PDF = "pdf", "PDF"
    DOCX = "docx", "DOCX"
    TXT = "txt", "TXT"
    CSV = "csv", "CSV"
    JSON = "json", "JSON"
    OTHER = "other", "Other"


class File(models.Model):
    PUBLIC = "public"
    PRIVATE = "private"

    VISIBILITY_CHOICES = [
        (PUBLIC, "Public"),
        (PRIVATE, "Private"),
    ]

    # === Core file fields ===
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(
        upload_to="user_files/",  # you might want to still use user_file_path if needed
        help_text="Upload a file to the user's file library. Supported types: pdf, docx, txt, csv, json",
    )
    file_type = models.CharField(
        max_length=10,
        choices=FileType.choices,
        default=FileType.PDF,
        help_text="Detected type of the uploaded file.",
    )
    gcs_path = models.CharField(max_length=1024, blank=True, null=True, help_text="Full GCS path of the uploaded file.")

    knowledge_base = models.ForeignKey(
        "KnowledgeBase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files",
        help_text="Knowledge base this file is attached to (if used for ingestion).",
    )

    # === Metadata and linkage ===
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_files"
    )
    team = models.ForeignKey("teams.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="files")
    source = models.CharField(max_length=255, blank=True, null=True)

    # === Status fields ===
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=PRIVATE)
    is_global = models.BooleanField(default=False, help_text="Global public library files.")
    is_ingested = models.BooleanField(
        default=False, help_text="Whether the file has been successfully ingested into the vector database."
    )

    # === Relationships ===
    tags = models.ManyToManyField(FileTag, related_name="files", blank=True)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="starred_files", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        creating = not self.pk

        # Detect file type and set gcs_path if needed
        if self.file:
            file_extension = os.path.splitext(self.file.name)[1].lower()
            file_type_map = {
                ".pdf": FileType.PDF,
                ".docx": FileType.DOCX,
                ".txt": FileType.TXT,
                ".csv": FileType.CSV,
                ".json": FileType.JSON,
            }
            self.file_type = file_type_map.get(file_extension, FileType.OTHER)

            if self.file_type == FileType.OTHER and hasattr(self.file, "content_type"):
                content_type_map = {
                    "application/pdf": FileType.PDF,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileType.DOCX,
                    "text/plain": FileType.TXT,
                    "text/csv": FileType.CSV,
                    "application/json": FileType.JSON,
                }
                self.file_type = content_type_map.get(self.file.content_type, FileType.OTHER)

            if not self.gcs_path:
                self.gcs_path = self.file.name

        super().save(*args, **kwargs)

        if getattr(self, "is_global", False) and creating:
            today = datetime.today()
            expected_prefix = f"global/library/{today.year}/{today.month:02d}/{today.day:02d}/"
            if not self.file.name.startswith(expected_prefix):
                original_path = self.file.name
                filename = os.path.basename(original_path)
                new_path = f"{expected_prefix}{filename}"

                file_content = default_storage.open(original_path).read()
                default_storage.save(new_path, ContentFile(file_content))  # ✅ wrap in ContentFile
                default_storage.delete(original_path)

                self.file.name = new_path
                self.gcs_path = new_path
                super().save(update_fields=["file", "gcs_path"])
            # ✅ Ingest into KB if needed

        # # ✅ After saving and moving, trigger ingestion if needed
        ## Add flag for auto ingestion
        # if self.knowledge_base and not self.is_ingested:
        #     try:
        #         ingest_single_file(
        #             file_path=self.gcs_path,
        #             vector_table_name=self.knowledge_base.vector_table_name,
        #         )
        #         self.is_ingested = True
        #         super().save(update_fields=["is_ingested"])
        #         print(f"✅ File {self.id} ingested successfully into {self.knowledge_base.vector_table_name}")
        #     except Exception as e:
        #         print(f"❌ Failed to ingest file {self.id}: {e}")

    def run_ingestion(self):
        """
        Manually trigger ingestion of this file.
        """
        if not self.knowledge_base:
            raise ValueError("No KnowledgeBase linked to this file.")

        if not self.gcs_path:
            raise ValueError("No GCS path set for this file.")

        try:
            ingest_single_file(
                file_path=self.gcs_path,
                vector_table_name=self.knowledge_base.vector_table_name,
            )
            self.is_ingested = True
            self.save(update_fields=["is_ingested"])
            print(f"✅ Successfully ingested File {self.id} into {self.knowledge_base.vector_table_name}")
        except Exception as e:
            print(f"❌ Manual ingestion failed for File {self.id}: {e}")
            raise e

    def delete(self, *args, **kwargs):
        """
        Deletes file from GCS when File object is deleted.
        """
        storage = self.file.storage
        file_name = self.file.name

        super().delete(*args, **kwargs)

        if storage.exists(file_name):
            storage.delete(file_name)

    def clean(self):
        super().clean()

        # Enforce KB linking only for superusers
        if self.knowledge_base and not (self.uploaded_by and self.uploaded_by.is_superuser):
            raise ValidationError("Only superadmins can upload files linked to a knowledge base.")

    @staticmethod
    def get_user_files(user_id, file_type=FileType.PDF):
        return File.objects.filter(uploaded_by=user_id, file_type=file_type)

    @staticmethod
    def get_team_files(team_id, file_type=FileType.PDF):
        return File.objects.filter(team=team_id, file_type=file_type)


###################
# Websites for crawling


class Website(BaseModel):
    url = models.URLField(max_length=500, unique=True, help_text="The website URL to be crawled.")
    name = models.CharField(max_length=255, blank=True, null=True, help_text="Optional name or label for the website.")
    description = models.TextField(blank=True, null=True, help_text="Optional description of the website.")
    owner = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="owned_websites", help_text="User who added this website."
    )
    tags = models.ManyToManyField(Tag, blank=True, help_text="Optional tags for organizing websites.")
    is_active = models.BooleanField(default=True, help_text="Whether this website is active and should be crawled.")
    last_crawled = models.DateTimeField(blank=True, null=True, help_text="Last time this website was crawled.")
    crawl_status = models.CharField(
        max_length=50,
        choices=[
            ("pending", "Pending"),
            ("crawling", "Crawling"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="pending",
        help_text="Current crawling status.",
    )

    def __str__(self):
        return self.name or self.url

    class Meta:
        ordering = ["-created_at"]  # Optional: order by newest first


## Models for Slack agent
# class SlackWorkspace(BaseModel):
#     team = models.ForeignKey(
#         "teams.Team",  # or settings.AUTH_USER_MODEL if you're not using teams
#         on_delete=models.CASCADE,
#         related_name="slack_workspaces",
#     )
#     slack_team_id = models.CharField(max_length=255, unique=True)  # Slack's team ID (Txxxxxxx)
#     slack_team_name = models.CharField(max_length=255)
#     access_token = models.CharField(max_length=255)  # xoxb-...
#     bot_user_id = models.CharField(max_length=255, null=True, blank=True)
#     installed_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.slack_team_name} ({self.slack_team_id})"


# Agent Tool Management models
class Tool(BaseModel):
    """
    Represents an external tool (e.g., GitHub, Notion) that agents can use.
    """

    name = models.CharField(max_length=100, unique=True)
    tool_identifier = models.CharField(
        max_length=100, unique=True, help_text="Used in code to identify the tool (e.g., 'github')"
    )
    description = models.TextField(blank=True, null=True)
    required_fields = models.JSONField(default=dict, help_text="Expected fields to initialize the tool")
    is_enabled = models.BooleanField(default=True, help_text="Controls availability for all users")

    def __str__(self):
        return f"{self.name} ({'Enabled' if self.is_enabled else 'Disabled'})"


class UserToolCredential(BaseModel):
    """
    A user's configuration for a tool. Can optionally be linked to a specific agent.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tool_credentials")
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="user_credentials")
    agent = models.ForeignKey(
        "Agent", on_delete=models.CASCADE, null=True, blank=True, related_name="user_tool_credentials"
    )
    credentials = Signer().sign(models.JSONField(help_text="Sensitive tool credentials"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "tool", "agent")

    def __str__(self):
        return f"{self.user} - {self.tool.name}" + (f" (Agent: {self.agent.name})" if self.agent else "")


class TeamToolCredential(BaseModel):
    """
    A shared team configuration for a tool. Can optionally be linked to a specific agent.
    """

    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="tool_credentials")
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="team_credentials")
    agent = models.ForeignKey(
        "Agent", on_delete=models.CASCADE, null=True, blank=True, related_name="team_tool_credentials"
    )
    credentials = Signer().sign(models.JSONField(help_text="Shared tool credentials for the team"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("team", "tool", "agent")

    def __str__(self):
        return f"{self.team} - {self.tool.name}" + (f" (Agent: {self.agent.name})" if self.agent else "")


# If you need encryption for fields, you can create a custom encrypted field:
class EncryptedTextField(models.TextField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.signer = Signer()

    def get_prep_value(self, value):
        if value is None:
            return value
        return self.signer.sign(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self.signer.unsign(value)

    def to_python(self, value):
        if value is None:
            return value

        try:
            return self.signer.unsign(value)
        except Exception:
            # You can handle or log the error here
            return value


## Knowledge base testing


class KnowledgeBasePdfURL(models.Model):
    kb = models.ForeignKey(
        "KnowledgeBase",
        on_delete=models.CASCADE,
        related_name="pdf_urls",
    )
    url = models.URLField(max_length=500)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_enabled = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("kb", "url")

    def __str__(self):
        return self.url
