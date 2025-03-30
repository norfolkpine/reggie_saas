# DEV
from typing import List
from agno.agent import Agent
from apps.agents.instructions import get_instructions
from your_django_app.models import ModelProvider
from agno.models.openai import OpenAIChat
from agno.models.google import Gemini
from agno.models.anthropic import Claude
from agno.models.groq import Groq
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.memory.db.postgres import PgMemoryDb
from agno.knowledge import AgentKnowledge
from agno.embedder.openai import OpenAIEmbedder
from agno.vectordb.pgvector import PgVector
from agno.tools.duckduckgo import DuckDuckGoTools

# Protect by using .env/secrets
db_url = "postgresql+psycopg://ai:ai@localhost:5532/ai"

def get_agent(agent_name: str, user_id: str, session_id: str) -> Agent:
    """Retrieve and initialize an agent from the database."""
    
    from reggie.models import Agent as DjangoAgent

    django_agent = DjangoAgent.objects.get(name=agent_name)
    model_provider = django_agent.model  

    if not model_provider or not model_provider.is_enabled:
        raise ValueError(f"Agent's assigned model is disabled or missing!")

    provider = model_provider.provider
    model_name = model_provider.model_name

    if provider == "openai":
        model = OpenAIChat(id=model_name)
    elif provider == "google":
        model = Gemini(id=model_name)
    elif provider == "anthropic":
        model = Claude(id=model_name)
    elif provider == "groq":
        model = Groq(id=model_name)
    else:
        raise ValueError(f"Unsupported model provider: {provider}")

    # Initialize memory for chat persistence
    memory = AgentMemory(
        db=PgMemoryDb(table_name=django_agent.session_table, db_url=db_url),
        create_user_memories=True,
        create_session_summary=True,
    )

    # Initialize knowledge base
    knowledge_base = AgentKnowledge(
        vector_db=PgVector(
            db_url=db_url,
            table_name="agentic_rag_documents",
            schema="ai",
            embedder=OpenAIEmbedder(id="text-embedding-ada-002", dimensions=1536),
        ),
        num_documents=3,
    )

    # Initialize the agent
    agent = Agent(
        name=django_agent.name,
        session_id=session_id,
        user_id=user_id,
        model=model,
        storage=PostgresAgentStorage(table_name=django_agent.session_table, db_url=db_url),
        memory=memory,
        knowledge=knowledge_base,
        description=django_agent.description,
        instructions=get_instructions(django_agent),
        search_knowledge=django_agent.search_knowledge,
        read_chat_history=django_agent.read_chat_history,
        tools=[DuckDuckGoTools()],
        markdown=True,
        show_tool_calls=django_agent.show_tool_calls,
        add_history_to_messages=True,
        add_datetime_to_instructions=True,
        debug_mode=django_agent.debug_mode,
        read_tool_call_history=django_agent.read_tool_call_history,
        num_history_responses=django_agent.num_history_responses,
    )

    return agent
