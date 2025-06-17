import logging
import time

from agno.agent import Agent
from django.core.cache import cache
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
    get_expected_output,
    get_instructions_tuple,
    get_llm_model,
    get_schema,
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

    def build(self) -> tuple[Agent, bool]:
        overall_start_time = time.time()
        logger.debug(
            f"[AgentBuilder] Starting build: agent_id={self.agent_id}, user_id={self.user.id}, session_id={self.session_id}"
        )

        cache_key = f"agent_instance_{self.agent_id}"
        cached_agent = cache.get(cache_key)

        if cached_agent:
            logger.info(f"Cache hit for agent_id: {self.agent_id}")
            # Update dynamic attributes if necessary, e.g., session_id, user_id
            cached_agent.session_id = self.session_id
            cached_agent.user_id = str(self.user.id)
            # Potentially re-evaluate instructions if they depend on the user
            user_instruction, other_instructions = get_instructions_tuple(self.django_agent, self.user)
            instructions = ([user_instruction] if user_instruction else []) + other_instructions
            cached_agent.instructions = instructions
            return cached_agent, True

        logger.info(f"Cache miss for agent_id: {self.agent_id}. Building agent.")
        # Ensure cached instances are initialized
        initialize_cached_instances() # Assuming this is quick and doesn't need timing

        t0 = time.time()
        model = get_llm_model(self.django_agent.model)
        logger.debug(f"[AgentBuilder] get_llm_model took {time.time() - t0:.4f}s")

        t0 = time.time()
        knowledge_base = build_knowledge_base(django_agent=self.django_agent)
        logger.debug(f"[AgentBuilder] build_knowledge_base took {time.time() - t0:.4f}s")

        t0 = time.time()
        is_knowledge_empty = False
        try:
            if hasattr(knowledge_base, "vector_db"): # Agno AgentKnowledge
                is_knowledge_empty = knowledge_base.vector_db.count() == 0
            elif hasattr(knowledge_base, "retriever"): # LlamaIndex LlamaIndexKnowledgeBase
                is_knowledge_empty = knowledge_base.retriever.index.docstore.num_docs == 0
        except Exception as e:
            logger.warning(f"[AgentBuilder] Failed to check knowledge base size: {e}")
        logger.debug(f"[AgentBuilder] Knowledge base emptiness check took {time.time() - t0:.4f}s. Empty: {is_knowledge_empty}")

        # Load instructions
        user_instruction, other_instructions = get_instructions_tuple(self.django_agent, self.user)
        instructions = ([user_instruction] if user_instruction else []) + other_instructions

        # Load expected output
        expected_output = get_expected_output(self.django_agent)

        logger.debug(
            f"[AgentBuilder] Model: {model.id} | Memory Table: {settings.AGENT_MEMORY_TABLE} | Vector Table: {self.django_agent.knowledge_base.vector_table_name if self.django_agent.knowledge_base else 'N/A'}"
        )

        t0 = time.time()
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
        logger.debug(f"[AgentBuilder] Agent instantiation took {time.time() - t0:.4f}s")

        logger.info(f"[AgentBuilder] Full build (cache miss) completed in {time.time() - overall_start_time:.2f}s")
        # Cache the newly built agent
        cache.set(cache_key, agent, timeout=3600)  # Cache for 1 hour
        logger.info(f"Agent {self.agent_id} cached.")
        return agent, False
