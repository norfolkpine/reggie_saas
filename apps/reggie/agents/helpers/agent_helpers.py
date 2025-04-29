# helpers/agent_helpers.py

from typing import Optional, Union

from django.conf import settings
from django.db.models import Q

from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge import AgentKnowledge
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.models.anthropic import Claude
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.models.openai import OpenAIChat
from agno.vectordb.pgvector import PgVector
from agno.knowledge.llamaindex import LlamaIndexKnowledgeBase

from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from sqlalchemy import create_engine

from apps.reggie.models import Agent as DjangoAgent
from apps.reggie.models import AgentInstruction, ModelProvider

db_url = settings.DATABASE_URL


### ====== AGENT INSTRUCTION HANDLING ====== ###

def get_instructions(agent: DjangoAgent, user):
    """
    Returns a single list of instructions, combining:
    - The instruction assigned to the agent (if enabled)
    - All system-level and global instructions (enabled)
    """
    instructions = []
    excluded_id = None

    if agent.instructions and agent.instructions.is_enabled:
        instructions.append(agent.instructions.instruction)
        excluded_id = agent.instructions.id

    system_global_qs = AgentInstruction.objects.filter(is_enabled=True).filter(
        Q(is_system=True) | Q(is_global=True)
    )

    if excluded_id:
        system_global_qs = system_global_qs.exclude(id=excluded_id)

    instructions += list(system_global_qs.values_list("instruction", flat=True))

    return instructions


def get_instructions_tuple(agent: DjangoAgent, user):
    """
    Returns a tuple:
      (user_instruction: Optional[str], other_instructions: List[str])
    """
    user_instruction = None
    excluded_id = None

    if agent.instructions and agent.instructions.is_enabled:
        user_instruction = agent.instructions.instruction
        excluded_id = agent.instructions.id

    other_instructions_qs = AgentInstruction.objects.filter(is_enabled=True).filter(
        Q(is_system=True)  # | Q(is_global=True)
    )

    if excluded_id:
        other_instructions_qs = other_instructions_qs.exclude(id=excluded_id)

    other_instructions = list(other_instructions_qs.values_list("instruction", flat=True))

    return user_instruction, other_instructions


### ====== AGENT OUTPUT HANDLING ====== ###

def get_expected_output(agent: DjangoAgent) -> Optional[str]:
    """
    Returns the expected output text from the agent, if enabled.
    """
    if agent.expected_output and agent.expected_output.is_enabled:
        return agent.expected_output.expected_output.strip()
    return None


### ====== MODEL PROVIDER SELECTION ====== ###

def get_llm_model(model_provider: ModelProvider):
    """
    Select the LLM model based on provider and model name.
    """
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
    """
    Build an AgentMemory backed by Postgres.
    """
    return AgentMemory(
        db=PgMemoryDb(table_name=table_name, db_url=db_url),
        create_user_memories=True,
        create_session_summary=True,
    )


### ====== KNOWLEDGE BASE BUILD (Dynamic) ====== ###

def build_knowledge_base(
    table_name: str,
    django_agent: DjangoAgent,
    db_url: str = db_url,
    schema: str = "ai",
) -> Union[AgentKnowledge, LlamaIndexKnowledgeBase]:
    """
    Dynamically build a knowledge base depending on the agent's knowledge type (Agno or LlamaIndex).
    """

    if not django_agent or not django_agent.knowledge_base:
        raise ValueError("Agent must have a linked KnowledgeBase to build knowledge base.")

    kb = django_agent.knowledge_base

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
            num_documents=3,
        )

    elif kb.knowledge_type == "llamaindex":
        engine = create_engine(db_url)
        vector_store = PGVectorStore(
            engine=engine,
            table_name=table_name,
            embed_dim=1536,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

        retriever = VectorIndexRetriever(index=index)
        return LlamaIndexKnowledgeBase(retriever=retriever)

    else:
        raise ValueError(f"Unsupported knowledge base type: {kb.knowledge_type}")
