import logging

from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.reggie.models import Agent as DjangoAgent

logger = logging.getLogger(__name__)


@receiver(post_save, sender=DjangoAgent)
def invalidate_agent_cache(sender, instance, **kwargs):
    """
    Invalidates the cache for an agent when the agent instance is saved.
    """
    cache_key = f"agent_instance_{instance.agent_id}"
    if cache.has_key(cache_key):
        cache.delete(cache_key)
        logger.info(f"Cache invalidated for agent_id: {instance.agent_id} due to model update.")
    else:
        logger.info(f"Cache key {cache_key} not found for agent_id: {instance.agent_id}. No invalidation needed.")

# Connect the signal handler
# This line is technically not needed here if @receiver decorator is used correctly,
# but it's good for explicitness and some Django versions/configurations.
# post_save.connect(invalidate_agent_cache, sender=DjangoAgent)
# Edit: Realized the @receiver decorator handles the connection.
# The line post_save.connect(...) is redundant if @receiver is used.
# logger.info("Agent cache invalidation signal connected.")
