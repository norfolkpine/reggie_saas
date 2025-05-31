from django.apps import AppConfig

class KnowledgeBasesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.knowledge_bases'
    verbose_name = 'Knowledge Bases'

    def ready(self):
        try:
            import apps.knowledge_bases.signals  # noqa F401
        except ImportError:
            pass
