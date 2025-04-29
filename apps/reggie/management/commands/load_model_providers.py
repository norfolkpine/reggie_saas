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

NOTE:
- Gemini models are loaded but DISABLED (is_enabled=False) by default.
- This is because LlamaIndex has not yet been updated to fully support dynamic models.
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
            # OpenAI models
            ("openai", "gpt-4o", "text-embedding-ada-002", 1536, "Flagship OpenAI model. Multimodal and fast."),
            ("openai", "gpt-4", "text-embedding-ada-002", 1536, "Powerful reasoning and coding. Slower than 4o."),
            ("openai", "gpt-3.5-turbo", "text-embedding-ada-002", 1536, "Cost-effective for chat and everyday tasks."),
            ("openai", "text-davinci-003", "text-embedding-ada-002", 1536, "Legacy instruction-tuned model."),
            ("openai", "text-davinci-002", "text-embedding-ada-002", 1536, "Earlier GPT-3 generation."),
            ("openai", "text-curie-001", "text-embedding-ada-002", 1536, "Smaller/faster GPT-3 model."),
            ("openai", "text-babbage-001", "text-embedding-ada-002", 1536, "Entry-level GPT-3 model."),
            ("openai", "text-ada-001", "text-embedding-ada-002", 1536, "Fastest and cheapest GPT-3 variant."),
            # Google Gemini models (disabled until LlamaIndex supports dynamic Gemini loading properly)
            ("google", "gemini-1.5-pro", "text-embedding-004", 768, "Latest high-end Gemini model (1.5 Pro)."),
            ("google", "gemini-1.5-flash", "text-embedding-004", 768, "Lightweight version of 1.5 for speed."),
            ("google", "gemini-1.0-pro", "text-embedding-004", 768, "Stable 1.0 Gemini Pro release."),
            ("google", "gemini-pro", "text-embedding-004", 768, "General Gemini model."),
            ("google", "gemini", "text-embedding-004", 768, "Legacy Gemini model."),
        ]

        if reset:
            qs = ModelProvider.objects.all()
            if provider_filter:
                qs = qs.filter(provider=provider_filter)
            count = qs.count()
            qs.delete()
            self.stdout.write(self.style.WARNING(f"⚠️  Deleted {count} existing model(s)."))

        for provider, model_name, embedder_id, dimensions, description in MODELS_TO_LOAD:
            if provider_filter and provider != provider_filter:
                continue

            # ✏️ Important: Gemini models are disabled by default
            is_enabled = provider != "google"

            obj, created = ModelProvider.objects.update_or_create(
                model_name=model_name,
                defaults={
                    "provider": provider,
                    "embedder_id": embedder_id,
                    "embedder_dimensions": dimensions,
                    "description": description,
                    "is_enabled": is_enabled,
                },
            )
            status = "✅ Created" if created else "↻ Updated"
            enabled_text = " (enabled)" if is_enabled else " (disabled)"
            self.stdout.write(f"{status}: {provider}:{model_name}{enabled_text}")
