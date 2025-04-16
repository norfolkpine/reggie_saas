import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ReggieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reggie"

    def ready(self):
        try:
            from agno.memory.db.postgres import create_table as create_memory_table
            from agno.storage.agent.postgres import create_table as create_storage_table
            from django.conf import settings

            from apps.reggie.helpers.agent_helpers import db_url

            create_storage_table(
                table_name=settings.AGENT_STORAGE_TABLE,
                db_url=db_url,
            )
            logger.info(f"[AgentStorage Init] Table ready: {settings.AGENT_STORAGE_TABLE}")

            create_memory_table(
                table_name=settings.AGENT_MEMORY_TABLE,
                db_url=db_url,
            )
            logger.info(f"[AgentMemory Init] Table ready: {settings.AGENT_MEMORY_TABLE}")

        except Exception as e:
            logger.warning(f"[AgentTable Init] Failed: {e}")
