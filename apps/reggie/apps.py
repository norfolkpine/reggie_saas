from django.apps import AppConfig


class ReggieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reggie"

    def ready(self):
        from . import signals  # noqa: F401
