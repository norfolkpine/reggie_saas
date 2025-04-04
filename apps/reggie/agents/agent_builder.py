# agent_builder.py

from agno.agent import Agent
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.duckduckgo import DuckDuckGoTools
from .tools.seleniumreader import SeleniumWebsiteReader
from .tools.blockscout import BlockscoutTools
from .tools.coingecko import CoinGeckoTools
from .tools.custom_slack import SlackTools

from apps.reggie.models import Agent as DjangoAgent
from .helpers.agent_helpers import (
    get_llm_model,
    build_agent_memory,
    build_knowledge_base,
    get_instructions,
    db_url,
)


class AgentBuilder:
    def __init__(self, agent_name: str, user, session_id: str):
        self.agent_name = agent_name
        self.user = user  # Django User instance
        self.session_id = session_id
        self.django_agent = self._get_django_agent()

    def _get_django_agent(self) -> DjangoAgent:
        return DjangoAgent.objects.get(name=self.agent_name)

    def build(self) -> Agent:
        model = get_llm_model(self.django_agent.model)
        memory = build_agent_memory(self.django_agent.session_table)
        knowledge_base = build_knowledge_base()

        # Get instructions: user-defined + admin/global
        user_instruction, other_instructions = get_instructions(self.django_agent, self.user)
        instructions = ([user_instruction] if user_instruction else []) + other_instructions

        # Get expected output format (if assigned)
        expected_output = (
            self.django_agent.expected_output.output_format
            if self.django_agent.expected_output else None
        )

        return Agent(
            name=self.django_agent.name,
            session_id=self.session_id,
            user_id=self.user.id,
            model=model,
            storage=PostgresAgentStorage(
                table_name=self.django_agent.session_table,
                db_url=db_url
            ),
            memory=memory,
            knowledge=knowledge_base,
            description=self.django_agent.description,
            instructions=instructions,
            expected_output=expected_output,
            search_knowledge=self.django_agent.search_knowledge,
            read_chat_history=self.django_agent.read_chat_history,
            tools=[DuckDuckGoTools()],
            markdown=self.django_agent.markdown_enabled,
            show_tool_calls=self.django_agent.show_tool_calls,
            add_history_to_messages=True,
            add_datetime_to_instructions=self.django_agent.add_datetime_to_instructions,
            debug_mode=self.django_agent.debug_mode,
            read_tool_call_history=self.django_agent.read_tool_call_history,
            num_history_responses=self.django_agent.num_history_responses,
        )
