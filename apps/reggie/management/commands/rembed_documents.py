# Not in use, may be used if we migrate from ada to small. Online reviews suggest ada is still better.
"""
from django.core.management.base import BaseCommand
from apps.reggie.models import Document
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.vectordb.pgvector import PgVector
from agno.knowledge.vector.utils import upsert_document_embedding

from django.conf import settings
import os

class Command(BaseCommand):
    help = "Re-embed all documents using text-embedding-3-small and update PgVector."

    def handle(self, *args, **kwargs):
        # Initialize the embedder
        embedder = OpenAIEmbedder(
            id="text-embedding-3-small",
            dimensions=1536
        )

        # Setup vector store
        vector_store = PgVector(
            db_url=settings.DATABASE_URL,  # Make sure this is set or replace with your actual connection string
            table_name="your_vector_table",
            schema="ai",
            embedder=embedder
        )

        # Re-embed each document
        docs = Document.objects.all()
        total = docs.count()

        for i, doc in enumerate(docs, start=1):
            try:
                # Simple: title + description
                text = f"{doc.title}\n{doc.description or ''}".strip()

                if not text:
                    self.stdout.write(self.style.WARNING(f"Skipping empty document: {doc.id}"))
                    continue

                # Generate & store embedding
                upsert_document_embedding(
                    vector_db=vector_store,
                    doc_id=str(doc.id),
                    text=text,
                    metadata={"source": "reembed", "title": doc.title}
                )
                self.stdout.write(f"✅ Re-embedded {i}/{total}: {doc.title}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed for {doc.id}: {e}"))

        self.stdout.write(self.style.SUCCESS("✨ Re-embedding complete!"))
 """