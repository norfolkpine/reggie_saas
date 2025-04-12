# helpers/agent_helpers.py
from typing import Optional

from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge import AgentKnowledge
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.models.anthropic import Claude
from agno.models.google import Gemini
from agno.models.groq import Groq
from agno.models.openai import OpenAIChat
from agno.vectordb.pgvector import PgVector
from django.conf import settings
from django.db.models import Q

from apps.reggie.models import Agent as DjangoAgent
from apps.reggie.models import AgentInstruction, ModelProvider

db_url = settings.DATABASE_URL
# def get_instructions(agent: DjangoAgent) -> List[str]:
#     return list(
#         AgentInstruction.objects.filter(agent=agent, is_enabled=True)
#         .values_list("instruction", flat=True)
#     )


# Agents have the base system instructions and then user added instructions
def get_instructions(agent: DjangoAgent, user):
    """
    Returns a single list of instructions, combining:
    - The instruction assigned to the agent (if enabled)
    - All system-level and global instructions (enabled)
    """
    instructions = []

    # Add the user-assigned instruction (if any)
    if agent.instructions and agent.instructions.is_enabled:
        instructions.append(agent.instructions.instruction)
        excluded_id = agent.instructions.id
    else:
        excluded_id = None

    # Add all system/global instructions, excluding the one already added
    system_global_qs = AgentInstruction.objects.filter(is_enabled=True).filter(Q(is_system=True) | Q(is_global=True))

    if excluded_id:
        system_global_qs = system_global_qs.exclude(id=excluded_id)

    instructions += list(system_global_qs.values_list("instruction", flat=True))

    return instructions


###
def get_instructions_tuple(agent: DjangoAgent, user):
    """
    Returns a tuple:
      (user_instruction: Optional[str], other_instructions: List[str])

    Includes:
    - The instruction directly assigned to the agent (if enabled)
    - All other enabled system/global instructions
    """
    user_instruction = None
    excluded_id = None

    # Assigned agent instruction (if enabled)
    if agent.instructions and agent.instructions.is_enabled:
        user_instruction = agent.instructions.instruction
        excluded_id = agent.instructions.id

    # All system/global instructions, excluding the one already added
    other_instructions_qs = AgentInstruction.objects.filter(is_enabled=True).filter(
        Q(is_system=True)  # | Q(is_global=True)
    )

    if excluded_id:
        other_instructions_qs = other_instructions_qs.exclude(id=excluded_id)

    other_instructions = list(other_instructions_qs.values_list("instruction", flat=True))

    return user_instruction, other_instructions


###


def get_expected_output(agent: DjangoAgent) -> Optional[str]:
    """
    Returns the expected output text from the agent, if enabled.
    """
    if agent.expected_output and agent.expected_output.is_enabled:
        return agent.expected_output.expected_output.strip()
    return None


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
        create_user_memories=True,  # Store user preferences
        create_session_summary=True,  # Store conversation summaries
    )


def build_knowledge_base(table_name: str, db_url: str = db_url, schema: str = "ai") -> AgentKnowledge:
    return AgentKnowledge(
        vector_db=PgVector(
            db_url=db_url,
            table_name=table_name,  # table_name="agentic_rag_documents",
            schema=schema,
            embedder=OpenAIEmbedder(
                id="text-embedding-ada-002", dimensions=1536
            ),  # this should be dictated by the model chosen
        ),
        num_documents=3,
    )


# def get_knowledge_table(agent: DjangoAgent) -> str:
#     if agent.knowledge_table:
#         return agent.knowledge_table
#     raise ValueError(f"Agent '{agent.name}' has no knowledge_table assigned.")
