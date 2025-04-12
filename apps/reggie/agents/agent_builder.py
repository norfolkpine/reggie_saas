# agent_builder.py
from agno.agent import Agent
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.duckduckgo import DuckDuckGoTools
from django.conf import settings

from apps.reggie.models import Agent as DjangoAgent

from .helpers.agent_helpers import (
    build_agent_memory,
    build_knowledge_base,
    db_url,
    get_expected_output,
    get_instructions_tuple,
    get_llm_model,
)
from .tools.blockscout import BlockscoutTools
from .tools.coingecko import CoinGeckoTools
from .tools.seleniumreader import SeleniumWebsiteReader


class AgentBuilder:
    def __init__(self, agent_id: str, user, session_id: str):
        self.agent_id = agent_id
        self.user = user  # Django User instance
        self.session_id = session_id
        self.django_agent = self._get_django_agent()

    def _get_django_agent(self) -> DjangoAgent:
        return DjangoAgent.objects.get(agent_id=self.agent_id)

    def build(self) -> Agent:
        model = get_llm_model(self.django_agent.model)
        # Memory table name
        memory = build_agent_memory(settings.AGENT_MEMORY_TABLE)  # self.django_agent.memory_table)
        #knowledge_base = build_knowledge_base(table_name=self.django_agent.knowledge_table)
        knowledge_base = self.django_agent.knowledge_base.vector_table_name

        # Get instructions: user-defined + admin/global
        user_instruction, other_instructions = get_instructions_tuple(self.django_agent, self.user)
        instructions = ([user_instruction] if user_instruction else []) + other_instructions

        expected_output = get_expected_output(self.django_agent)

        return Agent(
            name=self.django_agent.name,
            session_id=self.session_id,
            user_id=self.user.id,
            model=model,
            storage=PostgresAgentStorage(
                table_name="reggie_storage_sessions",  # self.django_agent.session_table,
                db_url=db_url,
            ),
            memory=memory,
            knowledge=knowledge_base,
            description=self.django_agent.description,
            instructions=instructions,
            expected_output=expected_output,
            search_knowledge=self.django_agent.search_knowledge,
            read_chat_history=self.django_agent.read_chat_history,
            tools=[DuckDuckGoTools(), SeleniumWebsiteReader(), CoinGeckoTools(), BlockscoutTools()],
            markdown=self.django_agent.markdown_enabled,
            show_tool_calls=self.django_agent.show_tool_calls,
            add_history_to_messages=True,
            add_datetime_to_instructions=self.django_agent.add_datetime_to_instructions,
            debug_mode=self.django_agent.debug_mode,
            read_tool_call_history=self.django_agent.read_tool_call_history,
            num_history_responses=self.django_agent.num_history_responses,
        )
