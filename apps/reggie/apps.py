from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class ReggieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reggie"

    def ready(self):
        try:
            from agno.storage.agent.postgres import PostgresAgentStorage
            from agno.memory.db.postgres import PgMemoryDb
            from django.conf import settings
            from apps.reggie.helpers.agent_helpers import db_url

            # Initialize shared agent storage
            storage = PostgresAgentStorage(
                table_name=settings.AGENT_STORAGE_TABLE,
                db_url=db_url,
            )
            logger.info(f"[AgentStorage Init] Storage ready: {settings.AGENT_STORAGE_TABLE}")

            # Initialize shared memory table
            memory_db = PgMemoryDb(
                table_name=settings.AGENT_MEMORY_TABLE,
                db_url=db_url,
            )
            logger.info(f"[AgentMemory Init] Memory DB ready: {settings.AGENT_MEMORY_TABLE}")

        except Exception as e:
            logger.warning(f"[Agent Init] Failed to initialize tables: {e}")
