# apps/reggie/helpers/agent_helpers.py

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
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
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


def build_knowledge_base(
    django_agent: DjangoAgent,
    user: settings.AUTH_USER_MODEL, # Added user argument
    db_url: str = get_db_url(),
    schema: str = "public",
    top_k: int = 3,
) -> Union[AgentKnowledge, LlamaIndexKnowledgeBase]:
    if not django_agent or not django_agent.knowledge_base:
        raise ValueError("Agent must have a linked KnowledgeBase.")

    kb = django_agent.knowledge_base
    # table_name = kb.vector_table_name # No longer needed here for agno_pgvector

    if kb.knowledge_type == "agno_pgvector":
        # Delegate to the KnowledgeBase model's method
        return kb.build_knowledge(num_documents=top_k)

    elif kb.knowledge_type == "llamaindex":
        if not kb.model_provider or not kb.model_provider.embedder_dimensions:
            raise ValueError(
                f"KnowledgeBase '{kb.name}' (ID: {kb.id}) of type 'llamaindex' "
                "must have a ModelProvider with embedder_dimensions set."
            )

        dimensions = kb.model_provider.embedder_dimensions
        physical_vector_table_name = f"vectorstore_dim_{dimensions}"

        vector_store = PGVectorStore(
            connection_string=db_url,
            async_connection_string=db_url.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=physical_vector_table_name, # Use physical table name
            embed_dim=dimensions, # Use dimensions from KB's model provider
            schema_name=schema,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

        # Construct filters list
        filters_list = [ExactMatchFilter(key="knowledgebase_id", value=kb.knowledgebase_id)]

        # Simplified RBAC-like filtering based on KB's direct associations
        if kb.project and hasattr(kb.project, 'uuid'):
            filters_list.append(ExactMatchFilter(key="project_id", value=str(kb.project.uuid)))
        elif kb.team and hasattr(kb.team, 'id'): # Assuming kb.team.id is the UUID
            filters_list.append(ExactMatchFilter(key="team_id", value=str(kb.team.id)))
        elif kb.uploaded_by and hasattr(kb.uploaded_by, 'uuid'):
            # This implies only the uploader can access if no project/team is linked,
            # or if the user isn't part of the linked project/team (actual permission check is more complex).
            # For this subtask, we are just adding the filter if the fields exist on KB.
            # A real implementation would check user's relation to kb.uploaded_by.uuid for this filter.
            filters_list.append(ExactMatchFilter(key="user_id", value=str(kb.uploaded_by.uuid)))

        filters = MetadataFilters(filters=filters_list)

        semantic_retriever = VectorIndexRetriever(index=index, similarity_top_k=top_k, filters=filters)

        # Improve later with BM25 Retriever, requires changes to document ingestion
        # If keyword_retriever also hits the vector store, it would need filtering too.
        # For now, it uses the same semantic_retriever which is already filtered.
        hybrid_retriever = ManualHybridRetriever(
            semantic_retriever=semantic_retriever,
            keyword_retriever=semantic_retriever,  # using same for simplicity, already filtered
            alpha=0.5,
        )

        return LlamaIndexKnowledgeBase(retriever=hybrid_retriever)

    else:
        raise ValueError(f"Unsupported knowledge base type: {kb.knowledge_type}")
