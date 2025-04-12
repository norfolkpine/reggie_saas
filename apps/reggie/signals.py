from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.reggie.models import KnowledgeBase
from apps.reggie.utils.gcs import init_knowledgebase_gcs_structure


@receiver(post_save, sender=KnowledgeBase)
def create_kb_gcs_folder(sender, instance, created, **kwargs):
    if created and instance.unique_code:
        init_knowledgebase_gcs_structure(str(instance.unique_code))
