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

from apps.opie.models import ModelProvider


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
            ("openai", "gpt-5-mini", "text-embedding-ada-002", 1536, "A faster, cost-efficient version of GPT-5 for well-defined tasks.", 0.25, 2.00),
            ("openai", "gpt-5-nano", "text-embedding-ada-002", 1536, "Fastest, most cost-efficient version of GPT-5.", 0.05, 0.40),
            ("openai", "gpt-4.1", "text-embedding-ada-002", 1536, "Smartest non-reasoning model.", 2.00, 8.00),
            ("openai", "gpt-4.1-mini", "text-embedding-ada-002", 1536, "Smaller, faster version of GPT-4.1.", 0.40, 1.60),
            ("openai", "gpt-4.1-nano", "text-embedding-ada-002", 1536, "Fastest, most cost-efficient version of GPT-4.1.", 0.10, 0.40),
            ("openai", "gpt-4o-mini", "text-embedding-ada-002", 1536, "Fast, affordable small model for focused tasks.", 0.15, 0.60),
            ("openai", "gpt-4o", "text-embedding-ada-002", 1536, "Flagship OpenAI model. Multimodal and fast.", 2.50, 10.00),
            ("openai", "gpt-4", "text-embedding-ada-002", 1536, "Powerful reasoning and coding. Slower than 4o.", 30.00, 60.00),
            ("openai", "gpt-3.5-turbo", "text-embedding-ada-002", 1536, "Cost-effective for chat and everyday tasks.", 0.50, 1.50),
            ("openai", "text-davinci-002", "text-embedding-ada-002", 1536, "Earlier GPT-3 generation.", 2.00, 2.00),
            ("openai", "text-babbage-002", "text-embedding-ada-002", 1536, "Entry-level GPT-3 model.", 0.40, 0.40),
            # Google Gemini models (disabled until LlamaIndex supports dynamic Gemini loading properly)
            ("google", "gemini-1.5-pro", "text-embedding-004", 768, "Latest high-end Gemini model (1.5 Pro).", 2.50, 10.00),
            ("google", "gemini-1.5-flash", "text-embedding-004", 768, "Lightweight version of 1.5 for speed.", 0.15, 0.60),
            ("google", "gemini-2.0-flash", "text-embedding-004", 768, "Stable 1.0 Gemini Pro release.", 0.10, 0.70)
        ]

        if reset:
            qs = ModelProvider.objects.all()
            if provider_filter:
                qs = qs.filter(provider=provider_filter)
            count = qs.count()
            qs.delete()
            self.stdout.write(self.style.WARNING(f"⚠️  Deleted {count} existing model(s)."))

        for provider, model_name, embedder_id, dimensions, description, input_cost_per_1M, output_cost_per_1M in MODELS_TO_LOAD:
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
                    "input_cost_per_1M": input_cost_per_1M,
                    "output_cost_per_1M": output_cost_per_1M,
                    "is_enabled": is_enabled,
                },
            )
            status = "✅ Created" if created else "↻ Updated"
            enabled_text = " (enabled)" if is_enabled else " (disabled)"
            self.stdout.write(f"{status}: {provider}:{model_name}{enabled_text}")
