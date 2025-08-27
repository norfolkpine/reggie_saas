# agents.py
from agno.agent import Agent
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.duckduckgo import DuckDuckGoTools
from helpers.agent_helpers import build_agent_memory, build_knowledge_base, db_url, get_instructions, get_llm_model
from reggie.models import Agent as DjangoAgent


def get_agent(agent_id: str, user, session_id: str) -> Agent:
    django_agent = DjangoAgent.objects.get(agent_id=agent_id)
    model = get_llm_model(django_agent.model)
    memory = build_agent_memory(django_agent.session_table)
    knowledge_base = build_knowledge_base()

    user_instruction, other_instructions = get_instructions(django_agent, user)
    instructions = ([user_instruction] if user_instruction else []) + other_instructions

    return Agent(
        name=django_agent.name,
        session_id=session_id,
        user_id=user.id,
        model=model,
        storage=PostgresAgentStorage(
            table_name=django_agent.session_table,
            db_url=db_url,
        ),
        memory=memory,
        knowledge=knowledge_base,
        description=django_agent.description,
        instructions=instructions,
        expected_output=django_agent.expected_output.output_format if django_agent.expected_output else None,
        search_knowledge=django_agent.search_knowledge,
        read_chat_history=django_agent.read_chat_history,
        tools=[DuckDuckGoTools()],
        markdown=django_agent.markdown_enabled,
        show_tool_calls=django_agent.show_tool_calls,
        add_history_to_messages=True,
        add_datetime_to_instructions=django_agent.add_datetime_to_instructions,
        debug_mode=django_agent.debug_mode,
        read_tool_call_history=django_agent.read_tool_call_history,
        num_history_responses=django_agent.num_history_responses,
    )
