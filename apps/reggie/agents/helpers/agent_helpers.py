# apps/reggie/helpers/agent_helpers.py

from typing import Optional, Union

from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge import AgentKnowledge
from agno.knowledge.llamaindex import LlamaIndexKnowledgeBase
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.models.anthropic import Claude
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.models.openai import OpenAIChat
from agno.vectordb.pgvector import PgVector
from django.conf import settings
from django.db.models import Q
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.vector_stores.postgres import PGVectorStore

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
    """
    Retrieve the schema name for all agent-related tables (storage and memory).
    Returns:
        str: The schema name to use.
    """
    schema = getattr(settings, "AGENT_SCHEMA", None)
    if not schema or not isinstance(schema, str) or not schema.strip():
        return "ai"
    return schema.strip()


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
    elif provider == "anthropic":
        return Claude(id=model_name)
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


def build_knowledge_base(
    django_agent: DjangoAgent,
    db_url: str = get_db_url(),
    schema: str = "public",
    top_k: int = 3,
) -> Union[AgentKnowledge, LlamaIndexKnowledgeBase]:
    if not django_agent or not django_agent.knowledge_base:
        raise ValueError("Agent must have a linked KnowledgeBase.")

    kb = django_agent.knowledge_base
    table_name = kb.vector_table_name

    if kb.knowledge_type == "agno_pgvector":
        return AgentKnowledge(
            vector_db=PgVector(
                db_url=db_url,
                table_name=table_name,
                schema=schema,
                embedder=OpenAIEmbedder(
                    id="text-embedding-ada-002",
                    dimensions=1536,
                ),
            ),
            num_documents=top_k,
        )

    elif kb.knowledge_type == "llamaindex":
        vector_store = PGVectorStore(
            connection_string=db_url,
            async_connection_string=db_url.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=table_name,
            embed_dim=1536,
            schema_name=schema,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

        semantic_retriever = VectorIndexRetriever(index=index, similarity_top_k=top_k)

        # Improve later with BM25 Retriever, requires changes to document ingestion
        hybrid_retriever = ManualHybridRetriever(
            semantic_retriever=semantic_retriever,
            keyword_retriever=semantic_retriever,  # using same for simplicity
            alpha=0.5,
        )

        return LlamaIndexKnowledgeBase(retriever=hybrid_retriever)

    else:
        raise ValueError(f"Unsupported knowledge base type: {kb.knowledge_type}")
