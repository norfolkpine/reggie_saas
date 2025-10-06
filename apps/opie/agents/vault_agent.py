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
from agno.db.postgres.postgres import PostgresDb
from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.opie.models import Project, ProjectInstruction, ModelProvider

from .helpers.agent_helpers import (
    get_db_url,
    get_llm_model,
    get_schema,
)
from .tools.vault_files import VaultFilesTools
from .tools.run_agent import RunAgentTool

logger = logging.getLogger(__name__)

# Cache keys for vault agent
VAULT_CACHE_TTL = 60 * 30  # 30 minutes cache

# Initialize shared database
VAULT_DB = None


def initialize_vault_instances():
    """Initialize cached database instance for vault."""
    global VAULT_DB

    if VAULT_DB is None:
        VAULT_DB = PostgresDb(
            db_url=get_db_url(),
        )

class CustomLlamaIndexKnowledge:
    def __init__(self, retriever, **kwargs):
        self.retriever = retriever
        self.num_documents = kwargs.get('num_documents', 5)

    def search(self, query: str, num_documents: int = None) -> list:
        """Search using LlamaIndex retriever"""
        try:
            from llama_index.core.schema import Document
            
            num_docs = num_documents or self.num_documents
            nodes = self.retriever.retrieve(query)
            # Limit results to requested number
            limited_nodes = nodes[:num_docs] if nodes else []
            return [Document(text=node.text, metadata=node.metadata or {}) for node in limited_nodes]
        except Exception as e:
            logger.error(f"Error in LlamaIndex search: {e}")
            return []

    def add_document(self, document: str, metadata: dict = None) -> str:
        """Add document with metadata"""
        logger.info(f"Adding document with metadata: {metadata}")
        return f"doc_{hash(document)}"


class VaultAgent:
    """
    Simplified agent for vault-specific queries.
    Uses project-specific vector data from vault vector table.
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
        """Get instructions for the vault agent using database query by project_id and user_id."""
        instructions = []

        try:
            # First try to get the project's assigned instruction
            project_instruction = None
            if self.project.instruction and self.project.instruction.is_active:
                project_instruction = self.project.instruction

            # If no project instruction or want user-specific instruction,
            # query ProjectInstruction by user and project context
            if not project_instruction:
                # Look for user-created instructions that could apply to this project
                project_instruction = ProjectInstruction.objects.filter(
                    created_by=self.user.id,
                    is_active=True,
                    instruction_type='vault_chat'  # Assuming vault_chat type for vault agent
                ).first()

            if project_instruction:
                instructions.append(project_instruction.content)
            else:
                # Default vault instructions - optimized for token efficiency
                instructions.append("You are a Vault AI assistant. And Answer questions using only the vault documents. Don't mention the unrecognizable infomations like the ids and you should use project name, folder name, file names and somelike that. Be concise and cite sources.")

        except Exception as e:
            logger.warning(f"Error fetching project instruction: {e}")
            # Default vault instructions - optimized for token efficiency
            instructions.append("You are a Vault AI assistant. And Answer questions using only the vault documents. Don't mention the unrecognizable infomations like the ids and you should use project name, folder name, file names and somelike that. Be concise and cite sources.")

        # Add minimal system instruction
        instructions.append("You are a Vault AI assistant. And Answer questions using only the vault documents. Don't mention the unrecognizable infomations like the ids and you should use project name, folder name, file names and somelike that. Be concise and cite sources. State clearly if information is unavailable.")

        return instructions

    def _build_knowledge_base(self):
        """Build vault knowledge base using LlamaIndex (same as KB infrastructure)."""
        # Import LlamaIndex components (same as knowledge base uses)
        from llama_index.vector_stores.postgres import PGVectorStore
        from llama_index.core import VectorStoreIndex
        from llama_index.core.retrievers import VectorIndexRetriever
        from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, FilterOperator

        # Use vault vector table (set in environment or default)
        table_name = getattr(settings, "VAULT_PGVECTOR_TABLE", "vault_vector_table")

        # Build metadata filters for this project/user
        filter_dict = {
            "project_uuid": str(self.project_id),
            "user_uuid": str(self.user.uuid),
        }

        # Add folder_id filter if specified
        if self.folder_id is not None:
            filter_dict["folder_id"] = str(self.folder_id)

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
        filters_list = [
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
        ]

        # Add folder_id filter if specified
        if self.folder_id is not None:
            filters_list.append(
                MetadataFilter(
                    key="folder_id",
                    value=str(self.folder_id),
                    operator=FilterOperator.EQ
                )
            )

        filters = MetadataFilters(filters=filters_list)

        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=5,
            filters=filters
        )

        knowledge_base = CustomLlamaIndexKnowledge(retriever=retriever)

        return knowledge_base

    def build(self, model_name: str = "gpt-4-turbo", enable_reasoning: bool = False) -> Agent:
        """Build the vault agent."""
        t0 = time.time()
        logger.debug(
            f"[VaultAgent] Starting build: project_id={self.project_id}, user_id={self.user.id}, session_id={self.session_id}"
        )

        # Initialize cached instances
        initialize_vault_instances()

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
                    table_name = getattr(settings, "VAULT_PGVECTOR_TABLE", "vault_vector_table")
                    
                    # Build WHERE clause based on available filters
                    where_conditions = ["metadata_->>'project_uuid' = %s", "metadata_->>'user_uuid' = %s"]
                    params = [str(self.project_id), str(self.user.uuid)]

                    if self.folder_id is not None:
                        where_conditions.append("metadata_->>'folder_id' = %s")
                        params.append(str(self.folder_id))

                    where_clause = " AND ".join(where_conditions)
                    query = f"SELECT COUNT(*) FROM {get_schema()}.{table_name} WHERE {where_clause} LIMIT 1"

                    cursor.execute(query, params)
                    count = cursor.fetchone()[0]
                    is_knowledge_empty = count == 0
            except Exception as e:
                logger.warning(f"Could not check vault knowledge base: {e}")
                is_knowledge_empty = False

            with contextlib.suppress(Exception):
                cache.set(cache_key_kb_empty, is_knowledge_empty, timeout=VAULT_CACHE_TTL)

        agent = Agent(
            model=model,
            db=VAULT_DB,  
            knowledge=knowledge_base if not is_knowledge_empty else None,
            name=f"Vault Assistant - {self.project.name}",
            description=f"AI assistant for {self.project.name} vault",
            instructions=instructions,
            enable_user_memories=True,
            enable_session_summaries=True,
            add_history_to_context=False, 
            search_knowledge=not is_knowledge_empty,
            read_chat_history=True,
            tools=[VaultFilesTools(self.file_ids, self.project_id, self.folder_id, self.user),RunAgentTool(user=self.user, session_id=self.session_id)],  # Vault files tool for browsing and reading vault files
            markdown=True,
            debug_mode=settings.DEBUG,
            session_id=self.session_id, 
            user_id=str(self.user.id),  
            add_datetime_to_context=False,
            read_tool_call_history=False,
            num_history_runs=3,
            add_knowledge_to_context=True,
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

    def build(self, model_name: str = "gpt-4-turbo", enable_reasoning: bool = None) -> Agent:
        """Build the vault agent."""
        return self.vault_agent.build(
            model_name=model_name,
            enable_reasoning=enable_reasoning if enable_reasoning is not None else False
        )