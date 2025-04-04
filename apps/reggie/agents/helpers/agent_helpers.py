# helpers/agent_helpers.py
from typing import List
from apps.reggie.models import Agent as DjangoAgent, ModelProvider, AgentInstruction
from django.db.models import Q
from agno.models.openai import OpenAIChat
from agno.models.google import Gemini
from agno.models.anthropic import Claude
from agno.models.groq import Groq
from agno.memory.db.postgres import PgMemoryDb
from agno.memory import AgentMemory
from agno.knowledge import AgentKnowledge
from agno.vectordb.pgvector import PgVector
from agno.embedder.openai import OpenAIEmbedder


db_url = "postgresql+psycopg://ai:ai@localhost:5532/ai"  # ideally .env

# def get_instructions(agent: DjangoAgent) -> List[str]:
#     return list(
#         AgentInstruction.objects.filter(agent=agent, is_enabled=True)
#         .values_list("instruction", flat=True)
#     )

# Agents have the base system instructions and then user added instructions
def get_instructions(agent: DjangoAgent, user):
    """
    Returns a tuple:
      (user_instruction: str or None, other_instructions: List[str])

    Includes:
    - System instructions (is_system=True)
    - Global instructions (is_global=True)
    - User-specific instruction (latest one only)
    """
    base_qs = AgentInstruction.objects.filter(
        is_enabled=True
    ).filter(
        Q(is_system=True) |            # ✅ System-level
        Q(is_global=True) |            # ✅ Admin/global
        Q(agent=agent, user=user)      # ✅ User-specific
    )

    # Try to get the user's custom instruction
    user_qs = base_qs.filter(agent=agent, user=user).order_by("-created_at")
    user_instruction = user_qs.first().instruction if user_qs.exists() else None

    # All others, excluding the one already counted as user_instruction
    other_instructions = list(
        base_qs.exclude(id=user_qs.first().id if user_qs.exists() else None)
               .values_list("instruction", flat=True)
    )

    return user_instruction, other_instructions



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

def build_agent_memory(table_name: str) -> AgentMemory:
    return AgentMemory(
        db=PgMemoryDb(table_name=table_name, db_url=db_url),
        create_user_memories=True,
        create_session_summary=True,
    )

def build_knowledge_base(table_name: str) -> AgentKnowledge:
    return AgentKnowledge(
        vector_db=PgVector(
            db_url=db_url,
            table_name=table_name, #table_name="agentic_rag_documents",
            schema="ai",
            embedder=OpenAIEmbedder(id="text-embedding-ada-002", dimensions=1536),  # this should be dictated by the model chosen
        ),
        num_documents=3,
    )
