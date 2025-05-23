from django.core.management.base import BaseCommand

from apps.app_integrations.models import SupportedApp


class Command(BaseCommand):
    help = "Insert predefined SupportedApp entries into the database"

    def handle(self, *args, **options):
        apps_data = [
            {
                "key": "google_drive",
                "title": "Google Drive",
                "description": "Connect with Google Drive to manage your files and documents directly from the platform.",
                "icon_url": "https://upload.wikimedia.org/wikipedia/commons/1/12/Google_Drive_icon_%282020%29.svg",
            },
            {
                "key": "jira",
                "title": "Jira",
                "description": "Integrate with Jira for project and issue tracking with AI insights.",
                "icon_url": "https://www.svgrepo.com/show/376328/jira.svg",
            },
            {
                "key": "confluence",
                "title": "Confluence",
                "description": "Connect with Confluence for team collaboration, wikis, and documentation.",
                "icon_url": "https://www.svgrepo.com/show/353597/confluence.svg",
            },
            {
                "key": "slack",
                "title": "Slack",
                "description": "Connect with Slack for real-time messaging, alerts, and collaboration within your teams.",
                "icon_url": "https://upload.wikimedia.org/wikipedia/commons/d/d5/Slack_icon_2019.svg"
            }

        ]

        created, updated = 0, 0

        for app in apps_data:
            obj, was_created = SupportedApp.objects.update_or_create(
                key=app["key"],
                defaults={
                    "title": app["title"],
                    "description": app["description"],
                    "icon_url": app["icon_url"],
                    "is_enabled": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(f"✅ Insert complete. Created: {created}, Updated: {updated}")
