"""
# Enable or disable model providers in bulk

# Enable all OpenAI models
python manage.py toggle_model_providers --provider openai --enable

# Disable all OpenAI models
python manage.py toggle_model_providers --provider openai --disable

# Enable all Gemini models
python manage.py toggle_model_providers --provider google --enable

# Disable all Gemini models
python manage.py toggle_model_providers --provider google --disable

# Default behavior if no --enable/--disable flag is given = enable
python manage.py toggle_model_providers --provider google
"""

from django.core.management.base import BaseCommand

from apps.reggie.models import ModelProvider


class Command(BaseCommand):
    help = "Enable or disable model providers in bulk (e.g., OpenAI or Google Gemini)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            type=str,
            choices=["openai", "google"],
            required=True,
            help="Which provider to update (openai or google)",
        )
        parser.add_argument("--enable", action="store_true", help="Enable models (default if no flag is passed)")
        parser.add_argument("--disable", action="store_true", help="Disable models")

    def handle(self, *args, **options):
        provider = options["provider"]
        enable = options["enable"]
        disable = options["disable"]

        if enable and disable:
            self.stderr.write(self.style.ERROR("❌ You can't --enable and --disable at the same time. Pick one."))
            return

        if not enable and not disable:
            # Default behavior = enable
            enable = True

        models = ModelProvider.objects.filter(provider=provider)

        if not models.exists():
            self.stderr.write(self.style.ERROR(f"❌ No models found for provider: {provider}"))
            return

        models.update(is_enabled=enable)

        action = "enabled" if enable else "disabled"
        self.stdout.write(self.style.SUCCESS(f"✅ {models.count()} {provider.upper()} models {action} successfully."))
