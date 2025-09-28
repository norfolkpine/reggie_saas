import contextlib
import logging
import time

from agno.agent import Agent
from agno.db.postgres.postgres import PostgresDb
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools

from django.apps import apps
from django.conf import settings
from django.core.cache import cache

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
from .tools.filereader import FileReaderTools
from .tools.selenium_tools import WebsitePageScraperTools

logger = logging.getLogger(__name__)

# === Shared, cached tool instances ===
CACHED_TOOLS = [
    FileReaderTools(),
    GoogleSearchTools(),
    WebsitePageScraperTools(),
    CoinGeckoTools(),
    BlockscoutTools(),
]

# Initialize this as None, will be set when Django is ready
CACHED_DB = None


def initialize_cached_instances():
    """Initialize cached database instance for v2."""
    global CACHED_DB

    if CACHED_DB is None:
        CACHED_DB = PostgresDb(
            db_url=get_db_url(),
            # V2 handles memory and storage automatically
            # No need for separate table configurations
        )
    print(f"CACHED_DB is: {CACHED_DB}")
    print(f"Database URL: {get_db_url()}")


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

    CACHE_TTL = 60 * 60  # 1 hour

    def _cache_key(self, suffix: str) -> str:
        return f"agent:{self.agent_id}:{suffix}"

    def build(self, enable_reasoning: bool | None = None) -> Agent:
        t0 = time.time()
        logger.debug(
            f"[AgentBuilder] Starting build: agent_id={self.agent_id}, user_id={self.user.id}, session_id={self.session_id}"
        )

        # Ensure cached instances are initialized
        initialize_cached_instances()

        # Determine whether reasoning should be enabled
        reasoning_enabled = enable_reasoning if enable_reasoning is not None else self.django_agent.default_reasoning

        # Load model
        model = get_llm_model(self.django_agent.model)

        # Load knowledge base dynamically with RBAC support
        # Get team_id from user's current team
        from apps.teams.models import Membership
        user_team = None
        try:
            # Get user's primary team (you may want to adjust this logic)
            membership = Membership.objects.filter(user=self.user).first()
            if membership:
                user_team = str(membership.team.id)
        except Exception as e:
            logger.debug(f"Could not get user team: {e}")
        
        knowledge_base = build_knowledge_base(
            django_agent=self.django_agent,
            user=self.user,  # Pass the full user object for RBAC
            user_uuid=str(self.user.uuid) if hasattr(self.user, 'uuid') else str(self.user.id),
            team_id=user_team,
            knowledgebase_id=getattr(self.django_agent.knowledge_base, "knowledgebase_id", None),
        )

        # Determine if the knowledge base is empty or missing (cached to avoid slow DB count)
        cache_key_kb_empty = self._cache_key("kb_empty")
        is_knowledge_empty = cache.get(cache_key_kb_empty)

        if is_knowledge_empty is None:
            if knowledge_base is None:
                logger.warning("[AgentBuilder] No knowledge base returned; disabling knowledge search")
                is_knowledge_empty = True
            else:
                is_knowledge_empty = False
                try:
                    vector_db = getattr(knowledge_base, "vector_db", None)
                    if vector_db is not None:
                        try:
                            # Use COUNT(*) only once per TTL to avoid repeated expensive scans
                            is_knowledge_empty = vector_db.count() == 0
                        except Exception:
                            logger.warning("[AgentBuilder] vector_db.count() unavailable; assuming non-empty")
                    else:
                        retriever = getattr(knowledge_base, "retriever", None)
                        if retriever is not None and getattr(retriever, "index", None) is not None:
                            try:
                                is_knowledge_empty = retriever.index.docstore.num_docs == 0
                            except Exception:
                                logger.warning("[AgentBuilder] Could not determine docstore size; assuming non-empty")
                except Exception as e:
                    logger.warning(f"[AgentBuilder] Failed to check knowledge base size: {e}")

            # Cache result to skip repeated checks for a while
            with contextlib.suppress(Exception):
                cache.set(cache_key_kb_empty, is_knowledge_empty, timeout=self.CACHE_TTL)

        # --- Load instructions (cached) ---
        cached_ins = cache.get(self._cache_key("instructions"))
        if cached_ins is not None:
            instructions = cached_ins
        else:
            user_instruction, other_instructions = get_instructions_tuple(self.django_agent, self.user)
            instructions = ([user_instruction] if user_instruction else []) + other_instructions
            # Only cache serialisable parts (content strings)
            with contextlib.suppress(Exception):
                cache.set(self._cache_key("instructions"), instructions, timeout=self.CACHE_TTL)

        # --- Load expected output (cached) ---
        expected_output = cache.get(self._cache_key("expected_output"))
        if expected_output is None:
            expected_output = get_expected_output(self.django_agent)
            with contextlib.suppress(Exception):
                cache.set(self._cache_key("expected_output"), expected_output, timeout=self.CACHE_TTL)

        # Fixed logging line (guard when knowledge base is None)
        try:
            vector_table_name = (
                getattr(getattr(self.django_agent, "knowledge_base", None), "vector_table_name", None)
                or "<none>"
            )
        except Exception:
            vector_table_name = "<unknown>"

        logger.debug(
            f"[AgentBuilder] Model: {model.id} | Database: {get_db_url()} | Vector Table: {vector_table_name}"
        )

        # Select toolset based on API flag
        tools = CACHED_TOOLS
        if reasoning_enabled:
            # Prepend ReasoningTools when reasoning is enabled so its instructions appear early
            tools = [ReasoningTools(add_instructions=True)] + tools

        # ✅ V2 Agent creation - simplified with automatic memory/storage
        agent = Agent(
            # V2 agent parameters
            model=model,
            db=CACHED_DB,  # ✅ Single database handles everything in v2
            knowledge=knowledge_base,
            
            # Agent configuration
            name=self.django_agent.name,
            description=self.django_agent.description,
            instructions=instructions,
            tools=tools,
            
            # V2 memory configuration (automatic)
            enable_user_memories=True,  # ✅ Replaces old AgentMemory
            enable_session_summaries=True,  # ✅ Replaces old session handling
            add_history_to_context=self.django_agent.add_history_to_messages,
            
            # Knowledge configuration
            search_knowledge=self.django_agent.search_knowledge and not is_knowledge_empty,
            
            # Display configuration
            markdown=self.django_agent.markdown_enabled,
            debug_mode=self.django_agent.debug_mode,
            
            # V2 specific configurations
            session_id=self.session_id,  # ✅ V2 handles sessions automatically
            user_id=str(self.user.id),   # ✅ V2 handles user context automatically
        )

        logger.debug(f"[AgentBuilder] Build completed in {time.time() - t0:.2f}s")
        return agent