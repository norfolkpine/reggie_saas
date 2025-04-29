from django.core.management.base import BaseCommand
from apps.reggie.utils.gcs_utils import get_storage_client
from django.conf import settings


class Command(BaseCommand):
    help = "Check connection to GCS bucket and list sample files."

    def handle(self, *args, **options):
        try:
            storage_client = get_storage_client()

            bucket_name = getattr(settings, "GCS_BUCKET_NAME", None)
            if not bucket_name:
                self.stderr.write(self.style.ERROR("❌ GCS_BUCKET_NAME not set in settings or .env"))
                return

            bucket = storage_client.bucket(bucket_name)

            # Try listing a few blobs
            blobs = list(bucket.list_blobs(max_results=5))

            if not blobs:
                self.stdout.write(self.style.WARNING("⚠️ Connected to GCS, but no files found in the bucket."))
            else:
                self.stdout.write(self.style.SUCCESS(f"✅ Successfully connected to GCS bucket '{bucket_name}'."))
                self.stdout.write("Sample files:")
                for blob in blobs:
                    self.stdout.write(f" - {blob.name}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Failed to connect to GCS: {str(e)}"))
