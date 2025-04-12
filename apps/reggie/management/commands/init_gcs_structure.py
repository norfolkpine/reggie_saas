import os
from django.core.management.base import BaseCommand
from django.conf import settings
from google.cloud import storage

from apps.users.models import CustomUser
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Initialize GCS base folder structure under reggie_app/"

    def handle(self, *args, **kwargs):
        client = storage.Client(credentials=settings.GS_CREDENTIALS)
        bucket = client.bucket(settings.GS_BUCKET_NAME)

        def ensure_folder(path: str):
            blob = bucket.blob(f"{path}/.keep")
            if not blob.exists():
                blob.upload_from_string("", content_type="text/plain")
                self.stdout.write(f"✅ Created: {path}/")
            else:
                self.stdout.write(f"✔️  Exists: {path}/")

        base_root = "reggie-data"

        # === Global Folders ===
        ensure_folder(f"{base_root}/global/knowledge_base")
        ensure_folder(f"{base_root}/global/library")

        # === Users ===
        for user in CustomUser.objects.all():
            base = f"{base_root}/users/{user.id}"
            ensure_folder(f"{base}/uploads")
            ensure_folder(f"{base}/agents")
            ensure_folder(f"{base}/projects")

        # === Teams ===
        for team in Team.objects.all():
            base = f"{base_root}/teams/{team.id}"
            ensure_folder(f"{base}/uploads")
            ensure_folder(f"{base}/projects")

        self.stdout.write(self.style.SUCCESS("✅ GCS folder structure initialized under reggie_app/."))
