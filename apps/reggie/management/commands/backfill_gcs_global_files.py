import os
from django.core.management.base import BaseCommand
from google.cloud import storage
from apps.reggie.models import File, FileTag
from django.conf import settings
from apps.reggie.utils.gcs_utils import get_storage_client



class Command(BaseCommand):
    help = "Backfill missing File entries from GCS (global folder only)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            type=str,
            default="reggie-data/global/",
            help="GCS prefix to scan (default: reggie-data/global/)"
        )
        parser.add_argument(
            "--bucket",
            type=str,
            default=None,
            help="GCS bucket name (default reads from GCS_BUCKET_NAME env variable)"
        )

    def handle(self, *args, **options):
        bucket_name = options["bucket"] or getattr(settings, "GCS_BUCKET_NAME", None)

        if not bucket_name:
            self.stderr.write(self.style.ERROR("❌ Missing bucket name. Set --bucket or GCS_BUCKET_NAME env variable."))
            return

        prefix = options["prefix"]

        storage_client = get_storage_client()
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)

        created_count = 0
        skipped_count = 0

        for blob in blobs:
            gcs_path = blob.name

            # Skip "folders" (GCS treats them as 0-size blobs sometimes)
            if gcs_path.endswith("/"):
                continue

            if File.objects.filter(gcs_path=gcs_path).exists():
                skipped_count += 1
                continue

            self.stdout.write(f"🆕 Creating File entry for {gcs_path}")

            File.objects.create(
                title=os.path.basename(gcs_path),
                description="Imported from GCS global folder",
                file=None,  # file field is not uploaded again
                gcs_path=gcs_path,
                is_ingested=False,
                is_global=True,
                visibility=File.PUBLIC,
            )
            created_count += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Done! {created_count} new File records created. {skipped_count} already existed."))
