import mimetypes
import os
import re
import uuid
from datetime import datetime

from agno.knowledge import AgentKnowledge
from agno.vectordb.pgvector import PgVector

# import psycopg2
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.signing import Signer
from django.db import models
from django.utils.text import slugify

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
class KnowledgeBaseType(models.TextChoices):
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
        default=KnowledgeBaseType.PDF,
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


## Documents Models
def user_document_path(instance, filename):
    """
    Generates path for file uploads to GCS, organized by user UUID and date.
    Example: reggie-data/users/45-550e8400e29b41d4a716446655440000/uploads/2025/04/13/filename.pdf
    """
    if instance.is_global:
        return f"reggie-data/global/library/{today.year}/{today.month:02d}/{today.day:02d}/{filename}"

    user = instance.uploaded_by
    folder = f"{user.id}-{user.uuid.hex}" if user else "anonymous"
    today = datetime.today()
    return f"reggie-data/users/{folder}/uploads/{today.year}/{today.month:02d}/{today.day:02d}/{filename}"

class DocumentTag(BaseModel):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class DocumentType(models.TextChoices):
    PDF = "pdf", "PDF"
    DOCX = "docx", "DOCX"
    TXT = "txt", "TXT"
    CSV = "csv", "CSV"
    JSON = "json", "JSON"
    OTHER = "other", "Other"


class Document(BaseModel):
    PUBLIC = "public"
    PRIVATE = "private"

    VISIBILITY_CHOICES = [
        (PUBLIC, "Public"),
        (PRIVATE, "Private"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(
        upload_to=user_document_path,
        help_text="Upload a file to the user's document library. Supported types: pdf, docx, txt, csv, json",
    )  # Automatically uploads to user-specific GCS folder
    file_type = models.CharField(
        max_length=10,
        choices=DocumentType.choices,
        default=DocumentType.PDF,
        help_text="Type of the file. Supported types: pdf, docx, txt, csv, json",
    )
    tags = models.ManyToManyField(DocumentTag, related_name="documents", blank=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=PRIVATE)
    is_global = models.BooleanField(default=False, help_text="Global public library document.")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_documents"
    )
    team = models.ForeignKey("teams.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    source = models.CharField(max_length=255, blank=True, null=True)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="starred_documents", blank=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.file:
            # Get the file extension
            file_extension = os.path.splitext(self.file.name)[1].lower()

            # Map extensions to types
            file_type_map = {
                ".pdf": DocumentType.PDF,
                ".docx": DocumentType.DOCX,
                ".txt": DocumentType.TXT,
                ".csv": DocumentType.CSV,
                ".json": DocumentType.JSON,
            }

            # Default to extension-based type
            self.file_type = file_type_map.get(file_extension, DocumentType.OTHER)

            # If extension didn't match, try mimetype
            if self.file_type == DocumentType.OTHER:
                guessed_mime, _ = mimetypes.guess_type(self.file.name)
                content_type_map = {
                    "application/pdf": DocumentType.PDF,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.DOCX,
                    "text/plain": DocumentType.TXT,
                    "text/csv": DocumentType.CSV,
                    "application/json": DocumentType.JSON,
                }
                self.file_type = content_type_map.get(guessed_mime, DocumentType.OTHER)

        super().save(*args, **kwargs)

    @staticmethod
    def get_user_documents(self, user_id, file_type=DocumentType.PDF):
        return Document.objects.filter(uploaded_by=user_id, file_type=file_type)

    @staticmethod
    def get_team_documents(self, team_id, file_type=DocumentType.PDF):
        return Document.objects.filter(team=team_id, file_type=file_type)


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
