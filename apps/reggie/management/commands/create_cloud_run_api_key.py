from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.api.models import UserAPIKey

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates an API key for the Cloud Run ingestion service'

    def handle(self, *args, **options):
        # Get or create a system user for Cloud Run
        user, created = User.objects.get_or_create(
            email='cloud-run-service@system.local',
            defaults={
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created system user for Cloud Run'))
        
        # Revoke any existing API keys for this user
        revoked_count = UserAPIKey.objects.filter(user=user, revoked=False).update(revoked=True)
        if revoked_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Revoked {revoked_count} existing API key(s)'))

        # Create API key
        api_key, key = UserAPIKey.objects.create_key(
            name="Cloud Run Ingestion Service",
            user=user
        )

        self.stdout.write(self.style.SUCCESS(f'''
API Key created successfully!

Add this to your Cloud Run service's environment variables:
DJANGO_API_KEY={key}

The key prefix is: {api_key.prefix}
''')) 