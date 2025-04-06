"""
# Load everything (default)
python manage.py load_model_providers

# Only OpenAI models
python manage.py load_model_providers --provider openai

# Only Gemini models
python manage.py load_model_providers --provider google

# Reset all existing records before loading
python manage.py load_model_providers --reset

# Reset only OpenAI models before loading them again
python manage.py load_model_providers --provider openai --reset

"""

from django.core.management.base import BaseCommand

from apps.reggie.models import ModelProvider


class Command(BaseCommand):
    help = "Load OpenAI and Gemini model providers with embedding config"

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider", type=str, choices=["openai", "google"], help="Filter by provider (e.g., openai, google)"
        )
        parser.add_argument(
            "--reset", action="store_true", help="Delete all existing model providers before loading new ones"
        )

    def handle(self, *args, **options):
        provider_filter = options["provider"]
        reset = options["reset"]

        MODELS_TO_LOAD = [
            # OpenAI
            ("openai", "gpt-4o", "text-embedding-ada-002", 1536),
            ("openai", "gpt-4", "text-embedding-ada-002", 1536),
            ("openai", "gpt-3.5-turbo", "text-embedding-ada-002", 1536),
            ("openai", "text-davinci-003", "text-embedding-ada-002", 1536),
            ("openai", "text-davinci-002", "text-embedding-ada-002", 1536),
            ("openai", "text-curie-001", "text-embedding-ada-002", 1536),
            ("openai", "text-babbage-001", "text-embedding-ada-002", 1536),
            ("openai", "text-ada-001", "text-embedding-ada-002", 1536),
            # Gemini
            ("google", "gemini-1.5-pro", "text-embedding-004", 768),
            ("google", "gemini-1.5-flash", "text-embedding-004", 768),
            ("google", "gemini-1.0-pro", "text-embedding-004", 768),
            ("google", "gemini-pro", "text-embedding-004", 768),
            ("google", "gemini", "text-embedding-004", 768),
        ]

        if reset:
            qs = ModelProvider.objects.all()
            if provider_filter:
                qs = qs.filter(provider=provider_filter)
            count = qs.count()
            qs.delete()
            self.stdout.write(self.style.WARNING(f"⚠️  Deleted {count} existing model(s)."))

        for provider, model_name, embedder_id, dimensions in MODELS_TO_LOAD:
            if provider_filter and provider != provider_filter:
                continue

            obj, created = ModelProvider.objects.update_or_create(
                model_name=model_name,
                defaults={
                    "provider": provider,
                    "embedder_id": embedder_id,
                    "embedder_dimensions": dimensions,
                    "is_enabled": True,
                },
            )
            status = "✅ Created" if created else "↻ Updated"
            self.stdout.write(f"{status}: {provider}:{model_name}")
