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

    CACHE_TTL = 60 * 60  # 1 hour

    def _cache_key(self, suffix: str) -> str:
        return f"agent:{self.agent_id}:{suffix}"

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
        knowledge_base = build_knowledge_base(
            django_agent=self.django_agent,
            user_uuid=self.user.uuid,
            knowledgebase_id=getattr(self.django_agent.knowledge_base, "knowledgebase_id", None),
        )

        # 🔥 Determine if the knowledge base is empty or missing (cached to avoid slow DB count)
        cache_key_kb_empty = self._cache_key("kb_empty")
        is_knowledge_empty = cache.get(cache_key_kb_empty)

        if is_knowledge_empty is None:
            if knowledge_base is None:
                logger.warning("[AgentBuilder] No knowledge base object returned by build_knowledge_base; assuming empty.")
                is_knowledge_empty = True
            else:
                is_knowledge_empty = True  # Default to empty, prove otherwise
                try:
                    # Try to get the filter_dict that was used to build/configure the knowledge_base
                    # This is stored by MultiMetadataLlamaIndexKnowledgeBase and MultiMetadataAgentKnowledge
                    relevant_filters = getattr(knowledge_base, 'filter_dict', None)

                    if not relevant_filters:
                        # Attempt to reconstruct essential filters if not directly available on KB object.
                        # This is a fallback and might not cover all cases perfectly.
                        # It's better if the KB object consistently carries its configuration.
                        logger.warning("[AgentBuilder] filter_dict not found on knowledge_base object. Attempting to reconstruct.")
                        relevant_filters = {}
                        if self.user and hasattr(self.user, 'uuid'):
                            relevant_filters["user_uuid"] = str(self.user.uuid)
                        if self.django_agent.knowledge_base and hasattr(self.django_agent.knowledge_base, 'knowledgebase_id'):
                            relevant_filters["knowledgebase_id"] = str(self.django_agent.knowledge_base.knowledgebase_id)
                        # Add other critical filters like team_id, project_id if they are part of the agent's context for KB
                        # For now, these two are the most common based on build_knowledge_base helper.
                        if not relevant_filters: # If still no filters, cannot perform a specific check
                            logger.warning("[AgentBuilder] Could not determine relevant_filters for KB empty check. Assuming empty for safety on shared tables.")
                            is_knowledge_empty = True # Safer to assume empty if filters are missing for a potentially filtered KB

                    if relevant_filters: # Only proceed if we have filters
                        # Case 1: Agno-style knowledge base with a `vector_db` attribute
                        vector_db = getattr(knowledge_base, "vector_db", None)
                        if vector_db is not None:
                            logger.debug(f"[AgentBuilder] Checking Agno PgVector for emptiness with filters: {relevant_filters}")
                            if hasattr(vector_db, 'exists_with_filter'): # Ideal: if agno.PgVector has a direct method
                                is_knowledge_empty = not vector_db.exists_with_filter(filter_dict=relevant_filters)
                            elif hasattr(vector_db, 'query_vectors'): # Fallback for Agno PgVector
                                # Query for 1 document with the filters. If anything returns, it's not empty.
                                # A dummy embedding is used if the query_vectors method primarily relies on metadata_filter.
                                # The query_str="concept" is a generic placeholder.
                                dummy_embedding = [0.0] * getattr(getattr(vector_db, 'embedder', None), 'dimensions', 1536) # Get dimensions if possible
                                results = vector_db.query_vectors(
                                    query_embedding=dummy_embedding,
                                    limit=1,
                                    metadata_filter=relevant_filters, # query_vectors must support this
                                    query_str="concept" # Placeholder query string
                                )
                                is_knowledge_empty = len(results) == 0
                            else: # Fallback to count with warning if other methods fail
                                logger.warning("[AgentBuilder] Agno vector_db.exists_with_filter or query_vectors not found, falling back to count() with filters. THIS MIGHT BE SLOW.")
                                # Assuming count() method on agno.PgVector can accept filter_dict
                                count_val = vector_db.count(filter_dict=relevant_filters) if hasattr(vector_db, 'count') else 0
                                is_knowledge_empty = count_val == 0
                            logger.debug(f"[AgentBuilder] Agno PgVector emptiness check result: {is_knowledge_empty}")

                        # Case 2: LlamaIndex-style knowledge base with a `retriever`
                        elif hasattr(knowledge_base, 'retriever') and hasattr(knowledge_base.retriever, 'index'):
                            logger.debug(f"[AgentBuilder] Checking LlamaIndex VectorStore for emptiness with filters: {relevant_filters}")
                            vector_store = knowledge_base.retriever.index.vector_store
                            if hasattr(vector_store, 'query'): # Check LlamaIndex PGVectorStore or similar
                                from llama_index.core.vector_stores.types import VectorStoreQuery, ExactMatchFilter, MetadataFilters as LIMetadataFilters

                                li_filters_list = []
                                for k, v_val in relevant_filters.items(): # Renamed v to v_val to avoid conflict
                                    li_filters_list.append(ExactMatchFilter(key=k, value=v_val))

                                # Dummy embedding, assuming the vector store is primarily filtered by metadata for this check
                                # The dimension should match the store's expected dimension.
                                # Attempt to get it from the knowledge_base or model_provider if available.
                                embed_dim = 1536 # Default
                                if hasattr(knowledge_base, 'model_provider') and hasattr(knowledge_base.model_provider, 'embedder_dimensions'):
                                    embed_dim = knowledge_base.model_provider.embedder_dimensions or 1536
                                elif hasattr(self.django_agent, 'model') and hasattr(self.django_agent.model, 'embedder_dimensions'):
                                    embed_dim = self.django_agent.model.embedder_dimensions or 1536

                                query_result = vector_store.query(
                                    VectorStoreQuery(
                                        query_embedding=[0.0] * embed_dim,
                                        similarity_top_k=1,
                                        filters=LIMetadataFilters(filters=li_filters_list)
                                    )
                                )
                                is_knowledge_empty = len(query_result.nodes) == 0
                            else: # Fallback for LlamaIndex if direct query not available
                                logger.warning("[AgentBuilder] LlamaIndex vector_store.query not available. Using retriever.retrieve(). THIS MIGHT BE SLOW or INACCURATE.")
                                # The retriever should already be configured with these filters by build_knowledge_base
                                nodes = knowledge_base.retriever.retrieve("concept") # Generic query
                                is_knowledge_empty = len(nodes) == 0
                            logger.debug(f"[AgentBuilder] LlamaIndex VectorStore emptiness check result: {is_knowledge_empty}")
                        else:
                            logger.warning("[AgentBuilder] Unknown knowledge base structure for empty check. Assuming empty.")
                            is_knowledge_empty = True
                    # If relevant_filters was empty after reconstruction attempts, is_knowledge_empty remains True (safer)

                except Exception as e:
                    logger.error(f"[AgentBuilder] Error during knowledge base empty check: {e}. Defaulting to non-empty to prevent breaking agents.", exc_info=True)
                    is_knowledge_empty = False # Fallback to ensure agent doesn't wrongly assume no knowledge if check fails

            # Cache result
            try:
                cache.set(cache_key_kb_empty, is_knowledge_empty, timeout=self.CACHE_TTL)
                logger.debug(f"[AgentBuilder] Cached kb_empty={is_knowledge_empty} for agent {self.agent_id}")
            except Exception as e:
                logger.warning(f"[AgentBuilder] Failed to cache kb_empty: {e}")
        else:
            logger.debug(f"[AgentBuilder] Using cached kb_empty={is_knowledge_empty} for agent {self.agent_id}")

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
