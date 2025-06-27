import logging
import time

from agno.agent import Agent
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.duckduckgo import DuckDuckGoTools
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
CACHED_DUMMY_KB = None  # Global shared dummy knowledge base for ultra-fast initialization


def initialize_cached_instances():
    """Initialize cached memory and storage instances."""
    global CACHED_MEMORY, CACHED_STORAGE, CACHED_DUMMY_KB

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
        
    # Create a global shared dummy knowledge base for ultra-fast agent initialization
    if CACHED_DUMMY_KB is None:
        from agno.knowledge import AgentKnowledge
        CACHED_DUMMY_KB = AgentKnowledge(vector_db=None, num_documents=3)
        CACHED_DUMMY_KB.metadata = {"has_content": False}


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

    def _check_knowledge_base_empty(self, knowledge_base):
        """Fast check to determine if knowledge base is empty WITHOUT expensive DB calls"""
        if knowledge_base is None:
            return True

        # Prefer metadata flag set at build time
        metadata = getattr(knowledge_base, "metadata", {}) or {}
        if "has_content" in metadata:
            return not bool(metadata["has_content"])

        # If we cannot determine, assume NOT empty to avoid costly checks
        return False

    def build(self) -> Agent:
        t0 = time.time()
        logger.debug(
            f"[AgentBuilder] Starting build: agent_id={self.agent_id}, user_id={self.user.id}, session_id={self.session_id}"
        )

        # Ensure cached instances are initialized
        initialize_cached_instances()

        # Try to get the complete agent from cache first
        agent_cache_key = self._cache_key("complete_agent")
        cached_agent_data = cache.get(agent_cache_key)
        
        if cached_agent_data and isinstance(cached_agent_data, dict):
            logger.debug(f"[AgentBuilder] Found complete cached agent for {self.agent_id}")
            # Only rebuild what's necessary for this session
            try:
                # These are the only things that might be different per session
                cached_agent = Agent(
                    agent_id=cached_agent_data['agent_id'],
                    name=cached_agent_data['name'],
                    session_id=self.session_id,  # New session ID
                    user_id=str(self.user.id),   # Current user
                    model=get_llm_model(cached_agent_data['model_id']),
                    storage=CACHED_STORAGE,
                    memory=CACHED_MEMORY,
                    knowledge=cached_agent_data['knowledge'],
                    description=cached_agent_data['description'],
                    instructions=cached_agent_data['instructions'],
                    expected_output=cached_agent_data['expected_output'],
                    search_knowledge=cached_agent_data['search_knowledge'],
                    read_chat_history=cached_agent_data['read_chat_history'],
                    tools=CACHED_TOOLS,
                    markdown=cached_agent_data['markdown'],
                    show_tool_calls=cached_agent_data['show_tool_calls'],
                    add_history_to_messages=cached_agent_data['add_history_to_messages'],
                    add_datetime_to_instructions=cached_agent_data['add_datetime_to_instructions'],
                    debug_mode=cached_agent_data['debug_mode'],
                    read_tool_call_history=cached_agent_data['read_tool_call_history'],
                    num_history_responses=cached_agent_data['num_history_responses'],
                )
                logger.debug(f"[AgentBuilder] Reused cached agent in {time.time() - t0:.2f}s")
                return cached_agent
            except Exception as e:
                logger.warning(f"Failed to restore cached agent: {e}, rebuilding...")
                # Fall through to rebuild                

        # --- Retrieve/calculate and cache static agent metadata (JSON-serialisable) ---
        metadata_key = self._cache_key("metadata")
        metadata = cache.get(metadata_key) or {}

        if metadata:
            logger.debug(f"[AgentBuilder] Metadata cache hit for agent {self.agent_id}")
            
        if not metadata:
            metadata = {
                "name": self.django_agent.name,
                "description": self.django_agent.description,
                "model_id": self.django_agent.model,
                "search_knowledge": self.django_agent.search_knowledge,
                "read_chat_history": self.django_agent.read_chat_history,
                "markdown": self.django_agent.markdown_enabled,
                "show_tool_calls": self.django_agent.show_tool_calls,
                "add_history_to_messages": self.django_agent.add_history_to_messages,
                "add_datetime_to_instructions": self.django_agent.add_datetime_to_instructions,
                "debug_mode": self.django_agent.debug_mode,
                "read_tool_call_history": self.django_agent.read_tool_call_history,
                "num_history_responses": self.django_agent.num_history_responses,
            }
            try:
                cache.set(metadata_key, metadata, timeout=self.CACHE_TTL)
            except Exception:
                pass

        # Load model (may need to re-instantiate but ID comes from cached metadata)
        t_model_start = time.time()
        model = get_llm_model(metadata["model_id"])
        logger.debug(f"[AgentBuilderTiming] Model load: {time.time() - t_model_start:.2f}s")

        # Try to get cached knowledge base
        kb_cache_key = self._cache_key("knowledge_base")
        knowledge_base = cache.get(kb_cache_key)
        
        # FAST PATH: Use hardcoded/dummy knowledge base to completely bypass LlamaIndex initialization
        # Check if we can use a fast path (when knowledge base isn't actually needed)
        use_fast_kb = not self.django_agent.search_knowledge or getattr(settings, 'AGENT_FAST_KB', False)
        
        if use_fast_kb:
            # Use the globally shared dummy knowledge base instance - ultra fast
            knowledge_base = CACHED_DUMMY_KB
            logger.debug(f"[AgentBuilder] Using FAST PATH knowledge base for {self.agent_id}")
        elif knowledge_base is None:
            # Standard path - Load knowledge base dynamically if not cached
            t_kb_start = time.time()
            knowledge_base = build_knowledge_base(
                django_agent=self.django_agent,
                user_uuid=self.user.uuid,
                knowledgebase_id=getattr(self.django_agent.knowledge_base, "knowledgebase_id", None),
            )
            logger.debug(f"[AgentBuilderTiming] Knowledge base build: {time.time() - t_kb_start:.2f}s")
            
            # Cache the knowledge base for future use
            try:
                cache.set(kb_cache_key, knowledge_base, timeout=self.CACHE_TTL)
            except Exception as e:
                logger.warning(f"Failed to cache knowledge base: {e}")
        else:
            logger.debug(f"[AgentBuilder] Using cached knowledge base for {self.agent_id}")

        # 🔥 Determine if the knowledge base is empty or missing (cached to avoid slow DB count)
        cache_key_kb_empty = self._cache_key("kb_empty")
        is_knowledge_empty = cache.get(cache_key_kb_empty)

        if is_knowledge_empty is None:
            is_knowledge_empty = self._check_knowledge_base_empty(knowledge_base)

            # Cache result to skip repeated checks for a while
            try:
                cache.set(cache_key_kb_empty, is_knowledge_empty, timeout=self.CACHE_TTL)
            except Exception:
                pass

        # --- Load instructions (cached) ---
        cached_ins = cache.get(self._cache_key("instructions"))
        if cached_ins is not None:
            instructions = cached_ins
        else:
            user_instruction, other_instructions = get_instructions_tuple(self.django_agent, self.user)
            instructions = ([user_instruction] if user_instruction else []) + other_instructions
            # Only cache serialisable parts (content strings)
            try:
                cache.set(self._cache_key("instructions"), instructions, timeout=self.CACHE_TTL)
            except Exception:
                pass

        # --- Load expected output (cached) ---
        expected_output = cache.get(self._cache_key("expected_output"))
        if expected_output is None:
            expected_output = get_expected_output(self.django_agent)
            try:
                cache.set(self._cache_key("expected_output"), expected_output, timeout=self.CACHE_TTL)
            except Exception:
                pass

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
        
        # Cache the complete agent configuration for future use
        try:
            cache_data = {
                'agent_id': str(self.django_agent.agent_id),
                'name': self.django_agent.name,
                # Don't store session_id as it changes
                # Don't store user_id as it changes
                'model_id': metadata["model_id"],
                # Don't store model as it's not serializable
                # storage and memory are global cached instances
                'knowledge': knowledge_base,
                'description': self.django_agent.description,
                'instructions': instructions,
                'expected_output': expected_output,
                'search_knowledge': self.django_agent.search_knowledge and not is_knowledge_empty,
                'read_chat_history': self.django_agent.read_chat_history,
                # tools are global cached instance
                'markdown': self.django_agent.markdown_enabled,
                'show_tool_calls': self.django_agent.show_tool_calls,
                'add_history_to_messages': self.django_agent.add_history_to_messages,
                'add_datetime_to_instructions': self.django_agent.add_datetime_to_instructions,
                'debug_mode': self.django_agent.debug_mode,
                'read_tool_call_history': self.django_agent.read_tool_call_history,
                'num_history_responses': self.django_agent.num_history_responses,
            }
            cache.set(agent_cache_key, cache_data, timeout=self.CACHE_TTL)
        except Exception as e:
            logger.warning(f"Failed to cache complete agent: {e}")

        logger.debug(f"[AgentBuilder] Build completed in {time.time() - t0:.2f}s")
        return agent
