# Standard library imports
import logging
import os
import re
import uuid
from datetime import datetime, timezone

# Agno imports
from agno.knowledge import AgentKnowledge
from agno.vectordb.pgvector import PgVector

# Third-party imports
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.signing import Signer
from django.db import models

# Ensure ValidationError is imported (it was already there but good to confirm)
from django.urls import reverse
from django.utils.text import slugify

# Local imports
from apps.reggie.utils.gcs_utils import ingest_single_file
from apps.teams.models import BaseTeamModel
from apps.users.models import CustomUser
from apps.utils.models import BaseModel

from .tasks import delete_vectors_from_llamaindex_task

logger = logging.getLogger(__name__)

INGESTION_STATUS_CHOICES = [
    ("not_started", "Not Started"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("failed", "Failed"),
]


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


class UserFeedback(BaseModel):
    FEEDBACK_TYPE_CHOICES = [
        ("good", "Good"),
        ("bad", "Bad"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="feedbacks"
    )
    session = models.ForeignKey(
        "ChatSession", on_delete=models.CASCADE, related_name="feedbacks", help_text="Related chat session."
    )
    chat_id = models.CharField(max_length=128, help_text="ID of the chat message or response being reviewed.")
    feedback_type = models.CharField(max_length=8, choices=FEEDBACK_TYPE_CHOICES)
    feedback_text = models.TextField(blank=True, null=True, help_text="Optional user feedback.")

    def __str__(self):
        return f"{self.user} - {self.session_id if hasattr(self, 'session_id') else self.session_id if hasattr(self, 'session_id') else self.session.id if self.session else None} - {self.feedback_type}"


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
    default_reasoning = models.BooleanField(
        default=False,
        help_text="Enable chain-of-thought reasoning by default for this agent.",
    )
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
        return f"{label}... ({scope}, {status})[{self.get_category_display()}]"


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
    """
    Represents a storage bucket configuration.
    Can be system-wide (team=None) or team-specific.
    """

    name = models.CharField(max_length=255, help_text="Display name for this storage configuration")
    provider = models.CharField(
        max_length=10, choices=StorageProvider.choices, default=StorageProvider.GCS, help_text="Storage provider type"
    )
    bucket_name = models.CharField(max_length=255, help_text="Actual bucket name (e.g. 'my-company-docs')")
    region = models.CharField(max_length=50, blank=True, null=True, help_text="Storage region (if applicable)")
    credentials = models.JSONField(
        null=True, blank=True, help_text="Storage credentials (encrypted). Not needed for system buckets."
    )
    is_system = models.BooleanField(default=False, help_text="Whether this is a system bucket (e.g. bh-reggie-media)")
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Team",
        help_text="Optional team. System buckets have no team.",
    )

    class Meta:
        unique_together = [("team", "bucket_name")]
        indexes = [
            models.Index(fields=["team", "is_system"], name="reggie_stor_team_id_1e43c2_idx"),
            models.Index(fields=["bucket_name"], name="reggie_stor_bucket__53379e_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.bucket_name})"

    def clean(self):
        super().clean()
        if self.is_system and self.team is not None:
            raise ValidationError("System buckets cannot be associated with a team")
        if not self.is_system and self.team is None:
            raise ValidationError("Non-system buckets must be associated with a team")

    def get_storage_url(self):
        """Returns the storage URL for this bucket based on provider"""
        if self.provider == StorageProvider.GCS:
            return f"gs://{self.bucket_name}"
        elif self.provider == StorageProvider.AWS_S3:
            return f"s3://{self.bucket_name}"
        return f"local://{self.bucket_name}"

    @property
    def bucket_url(self):
        """Returns the full bucket URL including region if applicable"""
        base_url = self.get_storage_url()
        if self.region and self.provider == StorageProvider.AWS_S3:
            return f"{base_url}?region={self.region}"
        return base_url

    @classmethod
    def get_system_bucket(cls):
        """
        Gets or creates the system storage bucket based on settings.
        """
        bucket = cls.objects.filter(is_system=True).first()
        if not bucket:
            # Determine provider from settings
            if settings.USE_GCS_MEDIA:
                provider = StorageProvider.GCS
                bucket_name = settings.GCS_BUCKET_NAME
            elif settings.USE_S3_MEDIA:
                provider = StorageProvider.AWS_S3
                bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            else:
                provider = StorageProvider.LOCAL
                bucket_name = "local-storage"

            bucket = cls.objects.create(
                name="System Storage",
                provider=provider,
                bucket_name=bucket_name,
                is_system=True,
                team=None,  # System bucket has no team
            )
        return bucket


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


# class ParserType(models.TextChoices):
#     PRESENTATION = "presentation", "Presentation/Slides"
#     LAWS = "laws", "Legal Documents"
#     MANUAL = "manual", "Manuals/Documentation"
#     PAPER = "paper", "Academic Papers"
#     RESUME = "resume", "Resumes/CVs"
#     BOOK = "book", "Books"
#     QA = "qa", "Q&A Format"
#     TABLE = "table", "Tabular Data"
#     NAIVE = "naive", "Simple Text"
#     PICTURE = "picture", "Image Content"
#     ONE = "one", "Single Document"
#     AUDIO = "audio", "Audio Transcripts"
#     EMAIL = "email", "Email Content"
#     KG = "knowledge_graph", "Knowledge Graph"
#     TAG = "tag", "Tagged Content"


class KnowledgeBasePermission(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ROLE_VIEWER = "viewer"
    ROLE_EDITOR = "editor"
    ROLE_OWNER = "owner"
    ROLE_CHOICES = [
        (ROLE_VIEWER, "Viewer"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_OWNER, "Owner"),
    ]
    knowledge_base = models.ForeignKey("KnowledgeBase", on_delete=models.CASCADE, related_name="permission_links")
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="knowledgebase_permission_links")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "users.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_kb_team_links"
    )

    class Meta:
        unique_together = ("knowledge_base", "team")
        verbose_name = "Knowledge Base Permission"
        verbose_name_plural = "Knowledge Base Permissions"


class KnowledgeBase(BaseModel):
    uploaded_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.CASCADE,
        related_name="knowledge_bases",
        help_text="User who created this knowledge base.",
        null=True,  # Allow null for easier migration; set after migration
        blank=True,  # Allow blank in forms
    )
    permissions = models.ManyToManyField(
        "teams.Team",
        through="KnowledgeBasePermission",
        related_name="knowledge_bases",
        blank=True,
        help_text="Teams with access to this knowledge base via permissions.",
    )
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
        editable=False,
        blank=True,
        help_text="Postgres vector table name used for embeddings.",
    )

    # Chunking settings
    chunk_size = models.IntegerField(default=1000, help_text="Size of chunks used for text splitting during ingestion.")
    chunk_overlap = models.IntegerField(default=200, help_text="Number of characters to overlap between chunks.")
    # parser_type = models.CharField(
    #     max_length=20,
    #     choices=ParserType.choices,
    #     null=True,
    #     blank=True,
    #     help_text="Semantic parser type that determines how the content is processed during ingestion."
    # )

    ## Add Subscriptions
    # subscriptions = models.ManyToManyField("djstripe.Subscription", related_name="knowledge_bases", blank=True)
    # team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, null=True, blank=True, related_name="knowledge_bases")

    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp when the knowledge base was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when the knowledge base was last updated.")

    def clean(self):
        super().clean()
        if self.pk is not None:  # If this is an update
            original = KnowledgeBase.objects.get(pk=self.pk)
            # Compare model_provider_id to avoid issues with None comparison if objects are None
            if original.model_provider_id != self.model_provider_id:
                raise ValidationError(
                    "Cannot change the Model Provider for an existing Knowledge Base. "
                    "This is to prevent conflicts with already generated embeddings. "
                    "Please create a new Knowledge Base for a different embedding model."
                )

    def save(self, *args, **kwargs):
        creating = not self.pk

        if creating:
            self.unique_code = generate_full_uuid()
            # Ensure model and name exist before generating agent_id
            provider_name = self.model_provider.provider if self.model_provider else "x"
            self.knowledgebase_id = generate_knowledgebase_id(provider_name, self.name)
            self.vector_table_name = "kb_" + settings.PGVECTOR_TABLE_PREFIX

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

    def check_vectors_exist(self, file_uuid: str) -> bool:
        """
        Check if vectors for a specific file exist in this knowledge base.
        """
        try:
            vector_db = self.build_knowledge().vector_db
            # Query for any vectors with the file's metadata
            result = vector_db.query_vectors(metadata_filter={"file_uuid": str(file_uuid)}, limit=1)
            return len(result) > 0
        except Exception as e:
            logger.error(f"Failed to check vectors for file {file_uuid} in KB {self.knowledgebase_id}: {e}")
            return False


## Projects
# Tag model for flexible categorization
class Tag(BaseModel):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


# Project model for grouping chats


class Project(BaseModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    # created_at = models.DateTimeField(auto_now_add=True)
    # updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="owned_projects")
    members = models.ManyToManyField(
        CustomUser, related_name="projects", blank=True, help_text="Direct users with access to this project."
    )
    shared_with_teams = models.ManyToManyField(
        "teams.Team", related_name="shared_projects", blank=True, help_text="Teams with access to this project."
    )
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
    title = models.CharField(max_length=255, default="New Chat", help_text="Title of the chat session")

    def __str__(self):
        return f"{self.title} ({self.agent.name})"

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["-updated_at"]),
            models.Index(fields=["user", "agent"]),
        ]


#######################

# Vault file path helper


def vault_file_path(instance, filename):
    """
    Determines GCS path for vault file uploads:
    - vault/project_uuid=.../year=YYYY/month=MM/day=DD/filename
    - vault/user_uuid=.../year=YYYY/month=MM/day=DD/filename
    """
    filename = filename.replace(" ", "_").replace("__", "_")
    today = datetime.today()
    date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"
    if getattr(instance, "project", None):
        return f"vault/project_uuid={instance.project.uuid}/{date_path}/{filename}"
    elif getattr(instance, "uploaded_by", None):
        return f"vault/user_uuid={instance.uploaded_by.uuid}/{date_path}/{filename}"
    else:
        return f"vault/anonymous/{date_path}/{filename}"


class VaultFile(models.Model):
    file = models.FileField(upload_to=vault_file_path, max_length=1024)
    original_filename = models.CharField(
        max_length=1024, blank=True, null=True, help_text="Original filename as uploaded by user"
    )
    project = models.ForeignKey("Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="vault_files")
    uploaded_by = models.ForeignKey("users.CustomUser", on_delete=models.CASCADE, related_name="vault_files")
    team = models.ForeignKey("teams.Team", null=True, blank=True, on_delete=models.SET_NULL, related_name="vault_files")
    shared_with_users = models.ManyToManyField("users.CustomUser", blank=True, related_name="shared_vault_files")
    shared_with_teams = models.ManyToManyField("teams.Team", blank=True, related_name="shared_team_vault_files")
    size = models.BigIntegerField(null=True, blank=True, help_text="Size of file in bytes")
    type = models.CharField(max_length=128, null=True, blank=True, help_text="File MIME type or extension")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Vault File"
        verbose_name_plural = "Vault Files"

    def __str__(self):
        return f"VaultFile({self.file.name}) by {self.uploaded_by}"


def user_document_path(instance, filename):
    """
    Generates path for file uploads to GCS, organized by user and date.
    Example: documents/45/2025/03/11/filename.pdf
    """
    user_id = instance.uploaded_by.id if instance.uploaded_by else "anonymous"
    today = datetime.today()
    date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"
    return f"document/{user_id}/{date_path}/{filename}"


## File Models (previously documents)
def user_file_path(instance, filename):
    """
    Determines GCS path for user file uploads:
    - User files go into 'user_files/user_uuid=.../year=YYYY/month=MM/day=DD/filename'
    - Global files go into 'global/library/year=YYYY/month=MM/day=DD/filename'
    """
    today = datetime.today()
    filename = filename.replace(" ", "_").replace("__", "_")
    date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"

    if getattr(instance, "is_global", False):
        return f"global/library/{date_path}/{filename}"
    elif getattr(instance, "uploaded_by", None):
        return f"user_files/user_uuid={instance.uploaded_by.uuid}/{date_path}/{filename}"
    else:
        return f"user_files/anonymous/{date_path}/{filename}"


def chat_file_path(instance, filename):
    """
    Determines GCS path for chat file uploads:
    - Chat files go into 'chat_files/user_uuid=.../session_id=.../year=YYYY/month=MM/day=DD/filename'
    """
    today = datetime.today()
    filename = filename.replace(" ", "_").replace("__", "_")
    date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"

    user_uuid = getattr(instance, "uploaded_by", None).uuid if getattr(instance, "uploaded_by", None) else "anonymous"
    session_id = getattr(instance, "session_id", "unknown")

    return f"chat_files/user_uuid={user_uuid}/session_id={session_id}/{date_path}/{filename}"


def vault_file_path(instance, filename):
    """
    Determines GCS path for vault file uploads:
    - Vault files go into 'vault/<project_id or user_uuid>/files/<filename>'
    """
    # Convert spaces to underscores in filename
    filename = filename.replace(" ", "_").replace("__", "_")
    user = getattr(instance, "uploaded_by", None)
    user_uuid = getattr(user, "uuid", None)
    filename = filename.replace(" ", "_").replace("__", "_")
    today = datetime.today()
    date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"
    if getattr(instance, "project", None):
        return f"vault/project_uuid={instance.project.uuid}/{date_path}/{filename}"
    elif getattr(instance, "uploaded_by", None):
        return f"vault/user_uuid={user_uuid}/{date_path}/{filename}"
    else:
        return f"vault/anonymous/{date_path}/{filename}"


def choose_upload_path(instance, filename):
    if getattr(instance, "is_vault", False):
        return vault_file_path(instance, filename)
    else:
        return user_file_path(instance, filename)


class FileTag(BaseModel):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


# === Shared Choices ===
INGESTION_STATUS_CHOICES = [
    ("not_started", "Not Started"),
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("failed", "Failed"),
]


class FileType(models.TextChoices):
    PDF = "pdf", "PDF"
    DOCX = "docx", "DOCX"
    TXT = "txt", "TXT"
    CSV = "csv", "CSV"
    JSON = "json", "JSON"
    OTHER = "other", "Other"


class Collection(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    # created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class File(models.Model):
    PUBLIC = "public"
    PRIVATE = "private"

    VISIBILITY_CHOICES = [
        (PUBLIC, "Public"),
        (PRIVATE, "Private"),
    ]

    # === Core file fields ===
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    filesize = models.BigIntegerField(
        default=0, help_text="Size of the file in bytes (mirrors file_size, for API compatibility)"
    )
    collection = models.ForeignKey(
        "Collection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="files",
        help_text="Collection this file belongs to.",
    )
    # Vault support
    vault_project = models.ForeignKey(
        "Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="file_vault_files",
        help_text="Vault project for this file (if any)",
    )
    is_vault = models.BooleanField(default=False, help_text="Is this file a vault file?")
    file = models.FileField(
        upload_to=choose_upload_path,
        max_length=1024,
        help_text="Upload a file to the user's file library or vault. Supported types: pdf, docx, txt, csv, json",
    )
    file_type = models.CharField(
        max_length=10,
        choices=FileType.choices,
        default=FileType.PDF,
        help_text="Detected type of the uploaded file.",
    )

    # === Storage fields ===
    storage_bucket = models.ForeignKey(
        StorageBucket, on_delete=models.SET_NULL, null=True, help_text="Storage bucket where this file is stored"
    )
    storage_path = models.CharField(
        max_length=1024, help_text="Full storage path including bucket (e.g. 'gcs://bucket/path' or 's3://bucket/path')"
    )
    original_path = models.CharField(
        max_length=1024, blank=True, null=True, help_text="Original path/name of the file before upload"
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
        default=False, help_text="Whether the file has been successfully ingested into any knowledge base."
    )
    auto_ingest = models.BooleanField(
        default=False, help_text="Whether to automatically ingest this file after upload."
    )
    total_documents = models.IntegerField(default=0, help_text="Total number of documents extracted from this file")
    page_count = models.IntegerField(default=0, help_text="Number of pages in the document (for PDFs)")
    file_size = models.BigIntegerField(default=0, help_text="Size of the file in bytes")
    # === Relationships ===
    tags = models.ManyToManyField(FileTag, related_name="files", blank=True)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="starred_files", blank=True)
    knowledge_bases = models.ManyToManyField(
        "KnowledgeBase",
        through="FileKnowledgeBaseLink",
        related_name="linked_files",
        blank=True,
        help_text="Knowledge bases this file is linked to for ingestion.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["uploaded_by", "file_type"]),
            models.Index(fields=["team", "file_type"]),
            models.Index(fields=["storage_bucket", "storage_path"]),
        ]
        permissions = [
            ("can_ingest_files", "Can ingest files into knowledge base"),
            ("can_manage_global_files", "Can manage global files"),
        ]

    def __str__(self):
        return self.title

    @property
    def gcs_path(self):
        """
        Returns the full GCS path for the file.
        This is used for compatibility with existing code that expects gcs_path.
        """
        if not self.storage_path:
            return None
        return self.storage_path

    def save(self, *args, **kwargs):
        creating = not self.pk

        # Set title to filename if not provided
        if creating and self.file and not self.title:
            # Convert spaces to underscores in filename
            filename = os.path.basename(self.file.name)
            filename = filename.replace(" ", "_").replace("__", "_")
            self.title = filename

        # Handle file type detection
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

        # If no storage bucket is set, use the system default
        if not self.storage_bucket:
            self.storage_bucket = StorageBucket.get_system_bucket()
            if not self.storage_bucket:
                raise ValidationError(
                    "No storage bucket configured. Please configure a system storage bucket or specify one explicitly."
                )

        if creating or "file" in kwargs.get("update_fields", []):
            if not self.file:
                raise ValidationError("No file provided for upload.")

            original_filename = os.path.basename(self.file.name)
            # Convert spaces to underscores in original filename
            original_filename = original_filename.replace(" ", "_").replace("__", "_")

            # Keep original filename but ensure uniqueness with UUID
            name, ext = os.path.splitext(original_filename)
            # Clean up the name part
            name = name.replace(" ", "_").replace("__", "_")
            unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"

            # Construct the full storage path
            new_path = f"{unique_filename}"

            try:
                if hasattr(self.file, "temporary_file_path"):
                    # If it's a TemporaryUploadedFile (large file)
                    with open(self.file.temporary_file_path(), "rb") as file_data:
                        default_storage.save(new_path, file_data)
                else:
                    # If it's an InMemoryUploadedFile (small file)
                    default_storage.save(new_path, self.file)

                # Update file paths
                self.file.name = new_path
                storage_url = self.storage_bucket.get_storage_url()
                if not storage_url:
                    raise ValidationError(f"Storage bucket '{self.storage_bucket}' returned invalid URL")

                # Handle path construction based on file type (global vs user)
                today = datetime.today()
                date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"

                if self.is_global:
                    self.storage_path = f"{storage_url}/global/library/{date_path}/{unique_filename}"
                else:
                    user_uuid = getattr(self.uploaded_by, "uuid", None)
                    self.storage_path = f"{storage_url}/user_uuid={user_uuid}/{date_path}/{unique_filename}"

                self.original_path = original_filename

                # Update title to match filename if it was auto-generated
                if self.title == os.path.basename(self.file.name):
                    self.title = unique_filename

            except ValidationError:
                raise
            except Exception as e:
                print(f"❌ Failed to save file {new_path}: {e}")
                raise ValidationError(f"Failed to save file: {str(e)}")

        # Set filesize to the actual file size if file exists
        if self.file and hasattr(self.file, "size"):
            self.filesize = self.file.size
        else:
            self.filesize = self.file_size  # fallback to file_size field if needed
        print(self)
        super().save(*args, **kwargs)

        # Only run ingestion if auto_ingest is True and we have linked knowledge bases
        if creating and self.auto_ingest and self.knowledge_bases.exists():
            try:
                self.run_ingestion()
            except Exception as e:
                logger.error(f"❌ Auto-ingestion failed for file {self.uuid}: {e}")
                # Don't raise the error - we want the file to be saved even if ingestion fails
                # The ingestion status will be marked as failed in the FileKnowledgeBaseLink

    def run_ingestion(self):
        """
        Manually trigger ingestion of this file into all linked knowledge bases.
        Each knowledge base gets its own vector store entries but references
        the same source file.
        """
        if not self.knowledge_bases.exists():
            raise ValueError("No KnowledgeBase linked to this file.")

        if not self.storage_path:
            raise ValueError("No storage path set for this file.")

        success_kbs = []
        failed_kbs = []

        for kb in self.knowledge_bases.all():
            try:
                # Get or create the link
                link, _ = FileKnowledgeBaseLink.objects.get_or_create(
                    file=self, knowledge_base=kb, defaults={"ingestion_status": "processing"}
                )

                # Update status to processing
                link.ingestion_status = "processing"
                link.ingestion_started_at = timezone.now()
                # Also save new ingestion parameters to the link for tracking/debugging
                if kb.model_provider:
                    link.embedding_model = kb.model_provider.embedder_id
                link.chunk_size = kb.chunk_size
                link.chunk_overlap = kb.chunk_overlap
                link.save(
                    update_fields=[
                        "ingestion_status",
                        "ingestion_started_at",
                        "embedding_model",
                        "chunk_size",
                        "chunk_overlap",
                    ]
                )

                if not kb.model_provider or not kb.model_provider.embedder_id:
                    logger.warning(
                        f"Skipping ingestion for File {self.id} into KB {kb.knowledgebase_id} "
                        f"due to missing ModelProvider or embedder_id on the KnowledgeBase."
                    )
                    link.ingestion_status = "failed"
                    link.ingestion_error = "KnowledgeBase is missing ModelProvider or embedder_id configuration."
                    link.save(update_fields=["ingestion_status", "ingestion_error"])
                    failed_kbs.append((kb, link.ingestion_error))
                    continue

                # Gather parameters for ingestion
                file_uuid_str = str(self.uuid)
                link_id_val = link.id
                embedding_provider_val = kb.model_provider.provider
                embedding_model_val = kb.model_provider.embedder_id
                chunk_size_val = kb.chunk_size
                chunk_overlap_val = kb.chunk_overlap

                # Perform the ingestion
                ingest_single_file(
                    file_path=self.storage_path,
                    vector_table_name=kb.vector_table_name,
                    file_uuid=file_uuid_str,
                    link_id=link_id_val,
                    embedding_provider=embedding_provider_val,
                    embedding_model=embedding_model_val,
                    chunk_size=chunk_size_val,
                    chunk_overlap=chunk_overlap_val,
                )

                # Update status to completed
                link.ingestion_status = "completed"
                link.ingestion_completed_at = timezone.now()
                link.save(update_fields=["ingestion_status", "ingestion_completed_at"])

                success_kbs.append(kb)
                print(f"✅ Successfully ingested File {self.id} into KB {kb.knowledgebase_id}")

            except Exception as e:
                failed_kbs.append((kb, str(e)))
                link.ingestion_status = "failed"
                link.ingestion_error = str(e)
                link.save(update_fields=["ingestion_status", "ingestion_error"])
                print(f"❌ Failed to ingest File {self.id} into KB {kb.knowledgebase_id}: {e}")

        # Update the overall file ingestion status
        self.is_ingested = len(success_kbs) > 0
        self.save(update_fields=["is_ingested"])

        if failed_kbs:
            errors = "\n".join([f"- KB {kb.knowledgebase_id}: {error}" for kb, error in failed_kbs])
            raise Exception(f"Ingestion failed for some knowledge bases:\n{errors}")

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

    def update_ingestion_progress(self, progress: float, processed_docs: int, total_docs: int):
        """
        Update ingestion progress for this file and its active knowledge base link.
        """
        # Update file's document count if not set
        if self.total_documents == 0 and total_docs > 0:
            self.total_documents = total_docs
            self.save(update_fields=["total_documents"])

        # Update the active knowledge base link
        active_link = self.knowledge_base_links.filter(ingestion_status="processing").first()

        if active_link:
            active_link.ingestion_progress = progress
            active_link.processed_docs = processed_docs
            active_link.total_docs = total_docs

            if progress >= 100:
                active_link.ingestion_status = "completed"
                active_link.ingestion_completed_at = timezone.now()
                # Update file's ingested status
                self.is_ingested = True
                self.save(update_fields=["is_ingested"])

            active_link.save(
                update_fields=[
                    "ingestion_progress",
                    "processed_docs",
                    "total_docs",
                    "ingestion_status",
                    "ingestion_completed_at",
                ]
            )

    def get_absolute_url(self):
        return reverse("file-detail", kwargs={"uuid": self.uuid})


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


class FileKnowledgeBaseLink(models.Model):
    """
    Manages the relationship between files and knowledge bases, including ingestion status.
    This allows a single file to be ingested into multiple knowledge bases.
    """

    file = models.ForeignKey("File", on_delete=models.CASCADE, related_name="knowledge_base_links")
    knowledge_base = models.ForeignKey("KnowledgeBase", on_delete=models.CASCADE, related_name="file_links")
    ingestion_status = models.CharField(
        max_length=20,
        choices=INGESTION_STATUS_CHOICES,
        default="not_started",
        help_text="Current status of the ingestion process for this file in this knowledge base.",
    )
    ingestion_error = models.TextField(blank=True, null=True, help_text="Error message if ingestion failed.")
    ingestion_started_at = models.DateTimeField(null=True, blank=True, help_text="When the ingestion process started.")
    ingestion_completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When the ingestion process completed."
    )
    ingestion_progress = models.FloatField(default=0.0, help_text="Current progress of ingestion (0-100)")
    processed_docs = models.IntegerField(default=0, help_text="Number of documents processed")

    total_docs = models.IntegerField(default=0, help_text="Total number of documents to process")
    embedding_model = models.CharField(
        max_length=100, blank=True, null=True, help_text="Model used for embeddings (e.g. text-embedding-ada-002)"
    )
    chunk_size = models.IntegerField(default=0, help_text="Size of chunks used for processing")
    chunk_overlap = models.IntegerField(default=0, help_text="Overlap between chunks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("file", "knowledge_base")
        indexes = [
            models.Index(fields=["file", "knowledge_base"]),
            models.Index(fields=["ingestion_status"]),
        ]

    def __str__(self):
        return f"{self.file.title} -> {self.knowledge_base.name} ({self.get_ingestion_status_display()})"

    def delete(self, *args, **kwargs):
        file_uuid_to_delete = None
        vector_table_name_to_delete_from = None

        if self.file and hasattr(self.file, "uuid"):
            file_uuid_to_delete = str(self.file.uuid)

        if self.knowledge_base and hasattr(self.knowledge_base, "vector_table_name"):
            vector_table_name_to_delete_from = self.knowledge_base.vector_table_name

        # Perform the actual deletion of the FileKnowledgeBaseLink instance
        super().delete(*args, **kwargs)

        # After successful deletion, if we have the necessary info, queue the task
        if file_uuid_to_delete and vector_table_name_to_delete_from:
            logger.info(
                f"Queuing Celery task to delete vectors for file_uuid: {file_uuid_to_delete} "
                f"from vector_table_name: {vector_table_name_to_delete_from}."
            )
            delete_vectors_from_llamaindex_task.delay(
                vector_table_name=vector_table_name_to_delete_from, file_uuid=file_uuid_to_delete
            )
        else:
            logger.warning(
                f"Could not queue vector deletion task for FileKnowledgeBaseLink (ID: {self.id}) "
                f"due to missing file_uuid ('{file_uuid_to_delete}') or "
                f"vector_table_name ('{vector_table_name_to_delete_from}')."
            )

    @property
    def progress_percentage(self):
        """Returns ingestion progress as a percentage."""
        if self.total_docs == 0:
            return 0.0
        return round((self.processed_docs / self.total_docs) * 100, 1)

    def mark_completed(self):
        """Mark this link as successfully completed."""
        self.ingestion_status = "completed"
        self.ingestion_completed_at = timezone.now()
        self.ingestion_progress = 100.0
        self.save(update_fields=["ingestion_status", "ingestion_completed_at", "ingestion_progress"])

        # Update file's ingested status
        if not self.file.is_ingested:
            self.file.is_ingested = True
            self.file.save(update_fields=["is_ingested"])


class EphemeralFile(BaseModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    uploaded_by = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    session_id = models.CharField(max_length=128)
    file = models.FileField(upload_to=chat_file_path)
    name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255)

    class Meta:
        indexes = [
            models.Index(fields=["session_id", "created_at"]),
        ]

    def __str__(self):
        return f"{self.name} (session: {self.session_id})"

    def to_agno_file(self):
        from agno.media import File as AgnoFile
        with self.file.open("rb") as f:
            return AgnoFile(name=self.name, content=f.read(), mime_type=self.mime_type)
