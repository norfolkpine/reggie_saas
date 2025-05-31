from django.db import models
from django.conf import settings
from apps.docs.models import Document  # Corrected import

class KnowledgeBase(models.Model):
    """
    Represents a collection of documents that can be queried.
    """
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='knowledge_bases',
        null=True, # Allow KBs not tied to a specific user initially, or for system KBs
        blank=True
    )
    vector_store_id = models.CharField(
        max_length=100,
        unique=True,
        blank=True, # Will be populated after creation and indexing
        help_text="Unique identifier for the vector store collection (e.g., ChromaDB collection name)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Knowledge Base"
        verbose_name_plural = "Knowledge Bases"

class KnowledgeBaseDocument(models.Model):
    """
    Links a Document from apps.docs to a KnowledgeBase.
    """
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='kb_documents' # Changed from 'documents' to avoid clash if KB has a 'documents' m2m field directly
    )
    document = models.ForeignKey(
        Document, # Corrected model name
        on_delete=models.CASCADE, # Or models.SET_NULL if you want to keep the link even if doc is deleted
        related_name='knowledge_base_associations'
    )
    added_at = models.DateTimeField(auto_now_add=True)
    # Potentially add metadata about the indexing status for this document within this KB
    # e.g., last_indexed_at, indexing_status ('pending', 'indexed', 'failed')

    def __str__(self):
        return f"'{self.document.name}' in KB '{self.knowledge_base.name}'"

    class Meta:
        ordering = ['-added_at']
        unique_together = ('knowledge_base', 'document') # Ensure a document is added only once to a KB
        verbose_name = "Knowledge Base Document"
        verbose_name_plural = "Knowledge Base Documents"
