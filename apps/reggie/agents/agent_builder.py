import logging
import time

from agno.agent import Agent
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.duckduckgo import DuckDuckGoTools
from django.apps import apps
from django.conf import settings

from apps.reggie.models import Agent as DjangoAgent

from .helpers.agent_helpers import (
    build_knowledge_base,
    get_db_url,
    get_schema,
    get_expected_output,
    get_instructions_tuple,
    get_llm_model,
)
from .tools.blockscout import BlockscoutTools
from .tools.coingecko import CoinGeckoTools
from .tools.seleniumreader import SeleniumWebsiteReader

logger = logging.getLogger(__name__)

# === Shared, cached tool instances ===
CACHED_TOOLS = [
    DuckDuckGoTools(),
    SeleniumWebsiteReader(),
    CoinGeckoTools(),
    BlockscoutTools(),
]

# Initialize these as None, will be set when Django is ready
CACHED_MEMORY = None
CACHED_STORAGE = None


def initialize_cached_instances():
    """Initialize cached memory and storage instances."""
    global CACHED_MEMORY, CACHED_STORAGE

    if CACHED_MEMORY is None:
        CACHED_MEMORY = AgentMemory(
            db=PgMemoryDb(table_name=settings.AGENT_MEMORY_TABLE, db_url=get_db_url(), schema=get_schema()),
            create_user_memories=True,
            create_session_summary=True,
        )

    if CACHED_STORAGE is None:
        CACHED_STORAGE = PostgresAgentStorage(
            table_name=settings.AGENT_STORAGE_TABLE,
            db_url=get_db_url(),
            schema=get_schema(),
        )


# Initialize when Django is ready
if apps.is_installed("django.contrib.admin"):
    initialize_cached_instances()


class AgentBuilder:
    def __init__(self, agent_id: str, user, session_id: str):
        self.agent_id = agent_id
        self.user = user  # Django User instance
        self.session_id = session_id
        self.django_agent = self._get_django_agent()

    def _get_django_agent(self) -> DjangoAgent:
        return DjangoAgent.objects.get(agent_id=self.agent_id)

    def build(self) -> Agent:
        t0 = time.time()
        logger.debug(
            f"[AgentBuilder] Starting build: agent_id={self.agent_id}, user_id={self.user.id}, session_id={self.session_id}"
        )

        # Ensure cached instances are initialized
        initialize_cached_instances()

        # Load model
        model = get_llm_model(self.django_agent.model)

        # Load knowledge base dynamically
        knowledge_base = build_knowledge_base(django_agent=self.django_agent)

        # 🔥 Check if knowledge base is empty
        is_knowledge_empty = False
        try:
            if hasattr(knowledge_base, "vector_db"):
                # Agno AgentKnowledge
                is_knowledge_empty = knowledge_base.vector_db.count() == 0
            elif hasattr(knowledge_base, "retriever"):
                # LlamaIndex LlamaIndexKnowledgeBase
                is_knowledge_empty = knowledge_base.retriever.index.docstore.num_docs == 0
        except Exception as e:
            logger.warning(f"[AgentBuilder] Failed to check knowledge base size: {e}")

        # Load instructions
        user_instruction, other_instructions = get_instructions_tuple(self.django_agent, self.user)
        instructions = ([user_instruction] if user_instruction else []) + other_instructions

        # Load expected output
        expected_output = get_expected_output(self.django_agent)

        # ✅ Fixed logging line
        logger.debug(
            f"[AgentBuilder] Model: {model.id} | Memory Table: {settings.AGENT_MEMORY_TABLE} | Vector Table: {self.django_agent.knowledge_base.vector_table_name}"
        )

        # Assemble the Agent
        agent = Agent(
            agent_id=str(self.django_agent.agent_id),
            name=self.django_agent.name,
            session_id=self.session_id,
            user_id=str(self.user.id),
            model=model,
            storage=CACHED_STORAGE,
            memory=CACHED_MEMORY,
            knowledge=knowledge_base,
            description=self.django_agent.description,
            instructions=instructions,
            expected_output=expected_output,
            search_knowledge=self.django_agent.search_knowledge and not is_knowledge_empty,
            read_chat_history=self.django_agent.read_chat_history,
            tools=CACHED_TOOLS,
            markdown=self.django_agent.markdown_enabled,
            show_tool_calls=self.django_agent.show_tool_calls,
            add_history_to_messages=self.django_agent.add_history_to_messages,
            add_datetime_to_instructions=self.django_agent.add_datetime_to_instructions,
            debug_mode=self.django_agent.debug_mode,
            read_tool_call_history=self.django_agent.read_tool_call_history,
            num_history_responses=self.django_agent.num_history_responses,
        )

        logger.debug(f"[AgentBuilder] Build completed in {time.time() - t0:.2f}s")
        return agent
