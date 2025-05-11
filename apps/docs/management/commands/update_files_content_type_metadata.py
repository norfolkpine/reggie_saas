# apps/docs/management/commands/update_files_content_type_metadata.py

from django.core.management.base import BaseCommand
from django.conf import settings
from google.cloud import storage as gcs
from apps.docs.models import Document
import magic


class Command(BaseCommand):
    help = "Update content-type metadata for GCS files"

    def handle(self, *args, **options):
        client = gcs.Client()
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        mime_detector = magic.Magic(mime=True)

        documents = Document.objects.all()
        self.stdout.write(f"[INFO] Found {documents.count()} documents. Starting ContentType fix...")

        for doc in documents:
            prefix = f"{doc.id}/attachments/"
            blobs = bucket.list_blobs(prefix=prefix)
            updated_count = 0

            for blob in blobs:
                if blob.name.endswith("/"):
                    continue

                if blob.content_type:
                    continue  # Already has content_type, skip

                try:
                    partial_data = blob.download_as_bytes(start=0, end=1023)
                    mime_type = mime_detector.from_buffer(partial_data)
                    blob.content_type = mime_type
                    blob.patch()
                    updated_count += 1
                except Exception as e:
                    self.stderr.write(f"[ERROR] Failed to update {blob.name}: {e}")

            if updated_count:
                self.stdout.write(f"[INFO] Updated {updated_count} blobs for Document {doc.id}")
