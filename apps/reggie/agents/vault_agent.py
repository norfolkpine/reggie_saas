"""
Vault Agent - A simplified agent for handling vault-specific queries using vault vector data.
This agent now uses the SAME LlamaIndex infrastructure as knowledge base for embedding and retrieval.
This ensures feature parity and eliminates code duplication.
"""

import contextlib
import logging
import time
from typing import Optional

from agno.agent import Agent
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.storage.agent.postgres import PostgresAgentStorage
from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.reggie.models import Project, ProjectInstruction

from .helpers.agent_helpers import (
    get_db_url,
    get_llm_model,
    get_schema,
)

logger = logging.getLogger(__name__)

# Cache keys for vault agent
VAULT_CACHE_TTL = 60 * 30  # 30 minutes cache

# Initialize shared memory and storage
VAULT_MEMORY = None
VAULT_STORAGE = None


def initialize_vault_instances():
    """Initialize cached memory and storage instances for vault."""
    global VAULT_MEMORY, VAULT_STORAGE

    if VAULT_MEMORY is None:
        VAULT_MEMORY = AgentMemory(
            db=PgMemoryDb(
                table_name=settings.VAULT_MEMORY_TABLE if hasattr(settings, 'VAULT_MEMORY_TABLE') else "ai.agent_memory_vault",
                db_url=get_db_url(),
                schema=get_schema()
            ),
            create_user_memories=True,
            create_session_summary=True,
        )

    if VAULT_STORAGE is None:
        VAULT_STORAGE = PostgresAgentStorage(
            table_name=settings.VAULT_STORAGE_TABLE if hasattr(settings, 'VAULT_STORAGE_TABLE') else "ai.agent_storage_vault",
            db_url=get_db_url(),
            schema=get_schema(),
        )


class VaultAgent:
    """
    Simplified agent for vault-specific queries.
    Uses project-specific vector data from data_vault_vector_table.
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        user,
        session_id: str,
        folder_id: Optional[str] = None,
        file_ids: Optional[list] = None,
    ):
        self.project_id = project_id
        self.user = user
        self.session_id = session_id
        self.folder_id = folder_id
        self.file_ids = file_ids or []
        self.project = self._get_project()
        self.agent_id = agent_id

    def _get_project(self) -> Project:
        """Get the project from database."""
        try:
            return Project.objects.get(uuid=self.project_id)
        except Project.DoesNotExist:
            raise ValueError(f"Project with id {self.project_id} not found")

    def _get_cache_key(self, suffix: str) -> str:
        """Generate cache key for vault agent."""
        return f"vault:{self.project_id}:{suffix}"

    def _get_instructions(self) -> list:
        """Get instructions for the vault agent."""
        instructions = []

        # Add project-specific instructions if available
        if self.project.instruction and self.project.instruction.is_active:
            instructions.append(self.project.instruction.content)
        else:
            # Default vault instructions - optimized for token efficiency
            instructions.append("You are a Vault AI assistant. Answer questions using only the vault documents. Be concise and cite sources.")

        # Add minimal system instruction
        instructions.append("Only use vault document content. State clearly if information is unavailable.")

        return instructions

    def _build_knowledge_base(self):
        """Build vault knowledge base using LlamaIndex (same as KB infrastructure)."""
        # Import LlamaIndex components (same as knowledge base uses)
        from llama_index.vector_stores.postgres import PGVectorStore
        from llama_index.core import VectorStoreIndex
        from llama_index.core.retrievers import VectorIndexRetriever
        from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, FilterOperator
        from agno.knowledge.llamaindex import LlamaIndexKnowledgeBase

        # Use vault vector table (set in environment or default)
        table_name = getattr(settings, 'VAULT_VECTOR_TABLE', 'vault_vector_table')

        # Build metadata filters for this project/user
        filter_dict = {
            "project_uuid": str(self.project_id),
            "user_uuid": str(self.user.uuid),
        }

        print("------------------------------------------------------------------------")
        print(f"Vault filters: {filter_dict}")
        print(f"Vault table: {table_name}")
        print("------------------------------------------------------------------------")

        # Create PGVectorStore (same schema as KB uses)
        vector_store = PGVectorStore(
            connection_string=get_db_url(),
            async_connection_string=get_db_url().replace("postgresql://", "postgresql+asyncpg://"),
            table_name=table_name,
            embed_dim=1536,
            schema_name=get_schema(),
        )

        # Create index from existing vector store
        index = VectorStoreIndex.from_vector_store(vector_store)

        # Create metadata filters for LlamaIndex
        filters = MetadataFilters(filters=[
            MetadataFilter(
                key="project_uuid",
                value=str(self.project_id),
                operator=FilterOperator.EQ
            ),
            MetadataFilter(
                key="user_uuid",
                value=str(self.user.uuid),
                operator=FilterOperator.EQ
            )
        ])

        # Create retriever with metadata filtering
        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=2,  # Reduce for token efficiency
            filters=filters
        )

        # Return LlamaIndex knowledge base (compatible with KB system)
        knowledge_base = LlamaIndexKnowledgeBase(retriever=retriever)

        return knowledge_base

    def build(self, model_name: str = "gpt-4", enable_reasoning: bool = False) -> Agent:
        """Build the vault agent."""
        t0 = time.time()
        logger.debug(
            f"[VaultAgent] Starting build: project_id={self.project_id}, user_id={self.user.id}, session_id={self.session_id}"
        )

        # Initialize cached instances
        initialize_vault_instances()

        # Get model - with automatic fallback for context length issues
        from apps.reggie.models import ModelProvider

        # Map models to their context limits and fallback options
        MODEL_CONTEXT_LIMITS = {
            "gpt-3.5-turbo": 4096,
            "gpt-3.5-turbo-16k": 16384,
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-4-turbo": 128000,
            "gpt-4-turbo-preview": 128000,
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
        }

        # If model has limited context, try to use a larger version
        original_model_name = model_name
        if model_name in ["gpt-4", "gpt-3.5-turbo"] and model_name in MODEL_CONTEXT_LIMITS:
            if MODEL_CONTEXT_LIMITS[model_name] < 16384:
                # Try to use a model with larger context
                fallback_models = {
                    "gpt-4": "gpt-4-turbo",
                    "gpt-3.5-turbo": "gpt-3.5-turbo-16k"
                }
                fallback_name = fallback_models.get(model_name)
                if fallback_name:
                    try:
                        fallback_provider = ModelProvider.objects.get(model_name=fallback_name, is_enabled=True)
                        model = get_llm_model(fallback_provider)
                        logger.info(f"[VaultAgent] Using {fallback_name} instead of {model_name} for larger context")
                        model_name = fallback_name
                    except ModelProvider.DoesNotExist:
                        logger.warning(f"[VaultAgent] Fallback model {fallback_name} not available, using {model_name}")

        try:
            model_provider = ModelProvider.objects.get(model_name=model_name, is_enabled=True)
            model = get_llm_model(model_provider)
        except ModelProvider.DoesNotExist:
            # Fallback to default model
            from agno.models.openai import OpenAIChat
            model = OpenAIChat(id=model_name)
            logger.warning(f"[VaultAgent] ModelProvider not found for {model_name}, using direct OpenAI model")

        # Load instructions (with caching)
        cache_key_ins = self._get_cache_key("instructions")
        cached_ins = cache.get(cache_key_ins)
        if cached_ins is not None:
            instructions = cached_ins
        else:
            instructions = self._get_instructions()
            with contextlib.suppress(Exception):
                cache.set(cache_key_ins, instructions, timeout=VAULT_CACHE_TTL)

        # Build knowledge base
        knowledge_base = self._build_knowledge_base()

        # Check if knowledge base is empty
        cache_key_kb_empty = self._get_cache_key("kb_empty")
        is_knowledge_empty = cache.get(cache_key_kb_empty)

        if is_knowledge_empty is None:
            try:
                # Quick check if there's any data
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {get_schema()}.data_vault_vector_table WHERE metadata_->>'project_uuid' = %s LIMIT 1",
                        [str(self.project_id)]
                    )
                    count = cursor.fetchone()[0]
                    is_knowledge_empty = count == 0
            except Exception as e:
                logger.warning(f"Could not check vault knowledge base: {e}")
                is_knowledge_empty = False

            with contextlib.suppress(Exception):
                cache.set(cache_key_kb_empty, is_knowledge_empty, timeout=VAULT_CACHE_TTL)

        # Expected output for vault - concise to save tokens
        expected_output = "Provide accurate responses with citations from vault documents."

        # Build the agent
        agent = Agent(
            agent_id=self.agent_id,
            name=f"Vault Assistant - {self.project.name}",
            session_id=self.session_id,
            user_id=str(self.user.id),
            model=model,
            storage=VAULT_STORAGE,
            memory=VAULT_MEMORY,
            knowledge=knowledge_base if not is_knowledge_empty else None,
            description=f"AI assistant for {self.project.name} vault",
            instructions=instructions,
            expected_output=expected_output,
            search_knowledge=not is_knowledge_empty,
            read_chat_history=True,
            tools=[],  # Vault agent doesn't need external tools
            markdown=True,
            show_tool_calls=False,
            add_history_to_messages=False,  # Disable to save tokens
            add_datetime_to_instructions=False,  # Disable to save tokens
            debug_mode=settings.DEBUG,
            read_tool_call_history=False,
            num_history_responses=1,  # Reduce from 3 to 1 to save tokens
            add_references=True,
        )

        logger.debug(f"[VaultAgent] Build completed in {time.time() - t0:.2f}s")
        return agent


class VaultAgentBuilder:
    """
    Builder class for vault agents, following the pattern of AgentBuilder.
    This is a convenience wrapper for consistency with existing code.
    """

    def __init__(
        self,
        project_id: str,
        user,
        session_id: str,
        agent_id: str,
        folder_id: Optional[str] = None,
        file_ids: Optional[list] = None,
    ):
        self.vault_agent = VaultAgent(
            project_id=project_id,
            user=user,
            agent_id=agent_id,
            session_id=session_id,
            folder_id=folder_id,
            file_ids=file_ids,
        )

    def build(self, model_name: str = "gpt-4", enable_reasoning: bool = None) -> Agent:
        """Build the vault agent."""
        return self.vault_agent.build(
            model_name=model_name,
            enable_reasoning=enable_reasoning if enable_reasoning is not None else False
        )