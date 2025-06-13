# apps/reggie/helpers/agent_helpers.py
import logging # Added for logger
from typing import Optional, Union

from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge import AgentKnowledge
from agno.knowledge.llamaindex import LlamaIndexKnowledgeBase
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb

# from agno.models.anthropic import Claude
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.models.openai import OpenAIChat
from agno.vectordb.pgvector import PgVector
from django.conf import settings
from django.db.models import Q
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter # Added for project_id filtering


from apps.reggie.agents.helpers.retrievers import ManualHybridRetriever  # 🔥 new
from apps.reggie.models import Agent as DjangoAgent
from apps.reggie.models import AgentInstruction, ModelProvider


def get_db_url() -> str:
    """Get the database URL from Django settings."""
    if not settings.DATABASE_URL:
        # If DATABASE_URL is not set, construct it from DATABASES settings
        db = settings.DATABASES["default"]
        return f"postgresql://{db['USER']}:{db['PASSWORD']}@{db['HOST']}:{db['PORT']}/{db['NAME']}"
    return settings.DATABASE_URL


def get_schema() -> str:
    """Get the schema name from Django settings, or use default 'ai'."""
    if not hasattr(settings, "AGENT_SCHEMA") or not settings.AGENT_SCHEMA:
        return "ai"
    return settings.AGENT_SCHEMA.strip()


### ====== AGENT INSTRUCTION HANDLING ====== ###


def get_instructions(agent: DjangoAgent, user):
    instructions = []
    excluded_id = None

    if agent.instructions and agent.instructions.is_enabled:
        instructions.append(agent.instructions.instruction)
        excluded_id = agent.instructions.id

    system_global_qs = AgentInstruction.objects.filter(is_enabled=True).filter(Q(is_system=True) | Q(is_global=True))

    if excluded_id:
        system_global_qs = system_global_qs.exclude(id=excluded_id)

    instructions += list(system_global_qs.values_list("instruction", flat=True))

    return instructions


def get_instructions_tuple(agent: DjangoAgent, user):
    user_instruction = None
    excluded_id = None

    if agent.instructions and agent.instructions.is_enabled:
        user_instruction = agent.instructions.instruction
        excluded_id = agent.instructions.id

    other_instructions_qs = AgentInstruction.objects.filter(is_enabled=True).filter(Q(is_system=True))

    if excluded_id:
        other_instructions_qs = other_instructions_qs.exclude(id=excluded_id)

    other_instructions = list(other_instructions_qs.values_list("instruction", flat=True))

    return user_instruction, other_instructions


### ====== AGENT OUTPUT HANDLING ====== ###


def get_expected_output(agent: DjangoAgent) -> Optional[str]:
    if agent.expected_output and agent.expected_output.is_enabled:
        return agent.expected_output.expected_output.strip()
    return None


### ====== MODEL PROVIDER SELECTION ====== ###


def get_llm_model(model_provider: ModelProvider):
    if not model_provider or not model_provider.is_enabled:
        raise ValueError("Agent's assigned model is disabled or missing!")

    model_name = model_provider.model_name
    provider = model_provider.provider

    if provider == "openai":
        return OpenAIChat(id=model_name)
    elif provider == "google":
        return Gemini(id=model_name)
    #    elif provider == "anthropic":
    #        return Claude(id=model_name)
    elif provider == "groq":
        return Groq(id=model_name)
    else:
        raise ValueError(f"Unsupported model provider: {provider}")


### ====== MEMORY DB BUILD ====== ###


def build_agent_memory(table_name: str) -> AgentMemory:
    return AgentMemory(
        db=PgMemoryDb(table_name=table_name, db_url=get_db_url()),
        create_user_memories=True,
        create_session_summary=True,
    )


### ====== KNOWLEDGE BASE BUILD (Dynamic) ====== ###


logger = logging.getLogger(__name__) # Added for logger

def build_knowledge_base(
    django_agent: DjangoAgent,
    project_id: str = None, # Added project_id
    db_url: str = get_db_url(),
    # schema: str = "public", # This schema was for PGVectorStore, LlamaIndex PGVectorStore uses 'public' by default if not specified. Agno PgVector uses get_schema() for 'ai'
    top_k: int = 3,
) -> Union[AgentKnowledge, LlamaIndexKnowledgeBase, None]: # Return None if KB is not configured
    if not django_agent.knowledge_base: # Check if agent has a KB linked
        logger.info(f"Agent {django_agent.agent_id} does not have a knowledge base configured. Skipping KB setup.")
        return None # Return None or an empty KB object if the agent can function without one

    kb = django_agent.knowledge_base
    table_name = kb.vector_table_name

    embed_dim = 1536 # Default
    if kb.model_provider and kb.model_provider.embedder_dimensions:
        embed_dim = kb.model_provider.embedder_dimensions
    else:
        logger.warning(
            f"KnowledgeBase '{kb.name}' (ID: {kb.id}) is using default embed_dim {embed_dim} "
            f"as model_provider or embedder_dimensions is not set. This could be problematic if incorrect."
        )

    if kb.knowledge_type == "agno_pgvector":
        if project_id:
            logger.warning(
                f"Project ID '{project_id}' provided for KnowledgeBase '{kb.name}' of type 'agno_pgvector'. "
                "This type does not currently support project_id filtering directly in build_knowledge_base."
            )
        return AgentKnowledge(
            vector_db=PgVector(
                db_url=db_url,
                table_name=table_name,
                schema=get_schema(), # Uses 'ai' schema from settings for Agno's PgVector
                embedder=kb.get_embedder(),
            ),
            num_documents=top_k,
        )

    elif kb.knowledge_type == "llamaindex":
        # For LlamaIndex, PGVectorStore uses 'public' schema by default for its tables.
        vector_store = PGVectorStore(
            connection_string=db_url,
            async_connection_string=db_url.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=table_name,
            embed_dim=embed_dim,
            # schema_name="public", # Explicitly 'public', or omit to use PGVectorStore's default.
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store, storage_context=storage_context)

        retriever_kwargs = {"similarity_top_k": top_k}
        if project_id:
            filters = MetadataFilters(filters=[ExactMatchFilter(key="project_id", value=str(project_id))])
            retriever_kwargs["filters"] = filters
            logger.info(f"LlamaIndex retriever for KB '{kb.name}' will use project_id filter: {project_id}")

        semantic_retriever = VectorIndexRetriever(index=index, **retriever_kwargs)

        hybrid_retriever = ManualHybridRetriever(
            semantic_retriever=semantic_retriever,
            keyword_retriever=semantic_retriever,
            alpha=0.5,
        )
        return LlamaIndexKnowledgeBase(retriever=hybrid_retriever)

    else:
        logger.error(f"Unsupported knowledge base type: {kb.knowledge_type} for KB ID {kb.id}")
        raise ValueError(f"Unsupported knowledge base type: {kb.knowledge_type}")
