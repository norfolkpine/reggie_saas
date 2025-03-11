from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.conf import settings
from apps.users.models import CustomUser
from apps.utils.models import BaseModel
from apps.teams.models import Team  # Reference Team model
from apps.utils.models import BaseModel
import os
from datetime import datetime


class Agent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="agents"
    )
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    knowledge_base = models.ForeignKey("KnowledgeBase", on_delete=models.CASCADE, null=True, blank=True)
    search_knowledge = models.BooleanField(default=True)
    add_datetime_to_instructions= models.BooleanField(default=True)
    show_tool_calls = models.BooleanField(default=False)
    markdown_enabled = models.BooleanField(default=True)

    is_global = models.BooleanField(default=False)  # flag for public agents
    created_at = models.DateTimeField(auto_now_add=True)

    subscriptions = models.ManyToManyField(
        "djstripe.Subscription", 
        related_name="agents", 
        blank=True
    )
    
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="agents"
    )

    def __str__(self):
        return self.name

    def is_accessible_by_user(self, user):
        """
        Check if a user can access this agent via global access, subscription, or team.
        """
        if self.is_global:
            return True  # Public agents are available to everyone

        if user.is_superuser:
            return True  # Admins get full access

        if self.team and self.team.members.filter(id=user.id).exists():
            return True  # Users in the team can access it

        if self.subscriptions.filter(customer__user=user, status="active").exists():
            return True  # Users with an active subscription can access

        return False
    
    def get_active_instructions(self):
        """Returns all enabled instructions for this agent, including global ones."""
        return AgentInstruction.objects.filter(
            models.Q(agent=self) | models.Q(is_global=True),
            is_enabled=True
        )



# Not using
class AgentParameter(models.Model):
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

class AgentInstruction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name="instructions"
    )
    agent = models.ForeignKey(
        "Agent", 
        on_delete=models.CASCADE, 
        related_name="instructions",
        null=True,  # Allows null if the instruction is global
        blank=True
    )
    instruction = models.TextField()
    category = models.CharField(
        max_length=50, 
        choices=InstructionCategory.choices, 
        default=InstructionCategory.PROCESS,
    )
    
    is_enabled = models.BooleanField(default=True)  # Allows enabling/disabling instructions
    is_global = models.BooleanField(default=False)  # New: Makes the instruction available to all agents
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "✅ Enabled" if self.is_enabled else "❌ Disabled"
        scope = "🌍 Global" if self.is_global else f"🔹 Agent: {self.agent.name if self.agent else 'N/A'}"
        return f"[{self.get_category_display()}] {self.instruction[:50]}... ({scope}, {status})"


# Storage Buckets
class StorageProvider(models.TextChoices):
    LOCAL = "local", "Local Storage"
    AWS_S3 = "aws_s3", "Amazon S3"
    GCS = "gcs", "Google Cloud Storage"

class StorageBucket(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="Name of the storage bucket (e.g., 'Main Tax Docs')")
    provider = models.CharField(
        max_length=10,
        choices=StorageProvider.choices,
        default=StorageProvider.LOCAL,
        help_text="Storage provider (Local, AWS S3, or Google Cloud Storage)."
    )
    bucket_url = models.CharField(
        max_length=500, 
        unique=True,
        help_text="Full storage bucket URL (e.g., 's3://my-bucket/', 'gcs://my-bucket/', or local path)"
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

class KnowledgeBase(models.Model):
    name = models.CharField(max_length=255, unique=True)
    knowledge_type = models.CharField(
        max_length=20, 
        choices=KnowledgeBaseType.choices, 
        default=KnowledgeBaseType.PDF,
        help_text="Defines how this knowledge base is structured (e.g., PDFs, SQL, API, etc.)."
    )
    path = models.CharField(
        max_length=500, 
        blank=True, 
        null=True, 
        help_text="Path for files or storage location (e.g., local dir, URL, S3 bucket)."
    )
    vector_table_name = models.CharField(max_length=255, unique=True, help_text="Vector database table name for embeddings.")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp when the knowledge base was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when the knowledge base was last updated.")

    def __str__(self):
        return f"{self.name} ({self.get_knowledge_type_display()})"
    

## Projects
# Tag model for flexible categorization
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

# Project model for grouping chats
class Project(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    #created_at = models.DateTimeField(auto_now_add=True)
    #updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='owned_projects')
    # Add shared team access to projects
    #members = models.ManyToManyField(CustomUser, related_name='projects', blank=True)
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name='projects',
        null=True,
        blank=True,
        help_text="Team this project belongs to (optional if personal)."
    )
    tags = models.ManyToManyField(Tag, blank=True)
    starred_by = models.ManyToManyField(CustomUser, related_name='starred_projects', blank=True)

    def __str__(self):
        return self.name
    
# Adding a model for Teams specific projects. This will be a future improvement
from apps.teams.models import BaseTeamModel

class TeamProject(BaseTeamModel):  # ✅ Inherits from BaseTeamModel to get `team` field
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True)
    starred_by = models.ManyToManyField(
        CustomUser,
        related_name='starred_team_projects',
        blank=True
    )

    def __str__(self):
        return self.name

 #######################   

## Documents Models
def user_document_path(instance, filename):
    """
    Generates path for file uploads to GCS, organized by user and date.
    Example: documents/45/2025/03/11/filename.pdf
    """
    user_id = instance.uploaded_by.id if instance.uploaded_by else 'anonymous'
    today = datetime.today()
    return f'documents/{user_id}/{today.year}/{today.month:02d}/{today.day:02d}/{filename}'


class DocumentTag(BaseModel):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Document(BaseModel):
    PUBLIC = 'public'
    PRIVATE = 'private'
    
    VISIBILITY_CHOICES = [
        (PUBLIC, 'Public'),
        (PRIVATE, 'Private'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to=user_document_path)  # Automatically uploads to user-specific GCS folder
    tags = models.ManyToManyField(DocumentTag, related_name='documents', blank=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=PRIVATE)
    is_global = models.BooleanField(default=False, help_text="Global public library document.")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents'
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents'
    )
    source = models.CharField(max_length=255, blank=True, null=True)
    starred_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='starred_documents',
        blank=True
    )

    def __str__(self):
        return self.title

###################