import time

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.opie.models import File
from apps.opie.utils.gcs_utils import ingest_single_file


class Command(BaseCommand):
    help = "Retry ingestion for all files where is_ingested=False"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=100, help="Max number of files to process in one run (default: 100)"
        )
        parser.add_argument(
            "--delay", type=int, default=1, help="Delay in seconds between each ingestion (default: 1 second)"
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        delay = options["delay"]

        files_to_ingest = File.objects.filter(is_ingested=False).order_by("created_at")[:limit]

        if not files_to_ingest:
            self.stdout.write(self.style.SUCCESS("✅ No un-ingested files found."))
            return

        success_count = 0
        fail_count = 0

        for file_obj in files_to_ingest:
            try:
                if not file_obj.gcs_path:
                    self.stderr.write(self.style.WARNING(f"⚠️ Skipping file {file_obj.id} (no gcs_path)"))
                    continue

                vector_table_name = (
                    file_obj.team.default_knowledge_base.vector_table_name if file_obj.team else "pdf_documents"
                )

                ingest_single_file(file_obj.gcs_path, vector_table_name)

                # ✅ Mark as ingested after successful call
                file_obj.is_ingested = True
                with transaction.atomic():
                    file_obj.save(update_fields=["is_ingested"])

                self.stdout.write(self.style.SUCCESS(f"✅ Successfully ingested file {file_obj.id}"))

                success_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"❌ Failed to ingest file {file_obj.id}: {e}"))
                fail_count += 1

            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(f"🎯 Done. {success_count} succeeded, {fail_count} failed."))
