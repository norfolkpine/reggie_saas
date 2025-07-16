import logging
import time
from typing import Optional, List, Union
from pathlib import Path

from agno.agent import Agent
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools

#from agno.tools.file_search import FileSearchTool
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
from .tools.seleniumreader import SeleniumTools
from .tools.direct_document_reader import DirectDocumentReaderTool, DocumentReaderTools

logger = logging.getLogger(__name__)

# === Shared, cached tool instances ===
CACHED_TOOLS = [
    # DuckDuckGoTools(),
    #FileSearchTool(),
    GoogleSearchTools(),
    SeleniumTools(),
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
    def __init__(self, agent_id: str, user, session_id: str, files: Optional[List[Union[str, Path]]] = None, ephemeral_files: Optional[List] = None):
        self.agent_id = agent_id
        self.user = user  # Django User instance
        self.session_id = session_id
        self.django_agent = self._get_django_agent()
        self.files = files
        self.ephemeral_files = ephemeral_files or []

    def _get_django_agent(self) -> DjangoAgent:
        return DjangoAgent.objects.get(agent_id=self.agent_id)

    CACHE_TTL = 60 * 60  # 1 hour

    def _cache_key(self, suffix: str) -> str:
        return f"agent:{self.agent_id}:{suffix}"

    def _prepare_file_paths(self) -> List[Union[str, Path]]:
        """Prepare file paths from both regular files and ephemeral files."""
        file_paths = []
        
        # Add regular files
        if self.files:
            file_paths.extend(self.files)
        
        # Add ephemeral files with proper validation
        if self.ephemeral_files:
            logger.debug(f"[DocumentReaderTools] Processing {len(self.ephemeral_files)} ephemeral files")
            for ef in self.ephemeral_files:
                try:
                    # Check if ephemeral file has the required attributes
                    if hasattr(ef, 'file') and ef.file:
                        # Get GCS URL for ephemeral files since they are stored in Google Cloud Storage
                        if hasattr(ef, 'get_gcs_url') and callable(getattr(ef, 'get_gcs_url')):
                            gcs_url = ef.get_gcs_url()
                            if gcs_url and gcs_url.startswith('gs://'):
                                file_paths.append(gcs_url)
                                logger.debug(f"[DocumentReaderTools] Added GCS file: {ef.name}")
                            else:
                                logger.warning(f"[DocumentReaderTools] Invalid GCS URL for {ef.name}: {gcs_url}")
                        else:
                            logger.warning(f"[DocumentReaderTools] EphemeralFile {ef.name} missing get_gcs_url method")
                    else:
                        logger.warning(f"[DocumentReaderTools] EphemeralFile {ef.name} missing file attribute")
                except Exception as e:
                    logger.error(f"[DocumentReaderTools] Error processing ephemeral file {ef.name}: {e}")
        
        logger.debug(f"[DocumentReaderTools] Total file paths prepared: {len(file_paths)}")
        return file_paths

    def build(self, enable_reasoning: Optional[bool] = None) -> Agent:
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
        print(f" self.ephemeral_files: {self.ephemeral_files}")

        # Load knowledge base dynamically
        knowledge_base = build_knowledge_base(
            django_agent=self.django_agent,
            user_uuid=self.user.uuid,
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

        # Fixed logging line
        logger.debug(
            f"[AgentBuilder] Model: {model.id} | Memory Table: {settings.AGENT_MEMORY_TABLE} | Vector Table: {self.django_agent.knowledge_base.vector_table_name}"
        )

        # Select toolset based on API flag
        tools = CACHED_TOOLS
        if reasoning_enabled:
            # Prepend ReasoningTools when reasoning is enabled so its instructions appear early
            tools = [ReasoningTools(add_instructions=True)] + tools

        # Add document reader tools if files are available
        print(f"[AgentBuilder] self.ephemeral_files: {self.ephemeral_files}")
        if self.ephemeral_files:
            logger.debug(f"[AgentBuilder] Found {len(self.ephemeral_files)} ephemeral files")
            for i, ef in enumerate(self.ephemeral_files):
                logger.debug(f"[AgentBuilder] Ephemeral file {i}: {ef.name} ({ef.mime_type})")
        file_paths = self._prepare_file_paths()
        # Diagnostic log: print type and repr of each file in file_paths
       
        if file_paths:
            logger.debug(f"[DocumentReaderTools] Adding toolkit with {len(file_paths)} files")
            try:
                document_tools = DocumentReaderTools(files=file_paths)
                tools.append(document_tools)
                logger.debug(f"[DocumentReaderTools] Successfully added to agent")
            except Exception as e:
                logger.error(f"[DocumentReaderTools] Failed to add toolkit: {e}")
        else:
            logger.debug(f"[DocumentReaderTools] No files available, skipping toolkit")

        # Log all tools being added
        logger.debug(f"[AgentBuilder] Total tools to be added: {len(tools)}")
        for i, tool in enumerate(tools):
            tool_name = getattr(tool, 'name', str(type(tool).__name__))
            logger.debug(f"[AgentBuilder] Tool {i+1}: {tool_name}")

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
            tools=tools,
            markdown=self.django_agent.markdown_enabled,
            show_tool_calls=self.django_agent.show_tool_calls,
            add_history_to_messages=self.django_agent.add_history_to_messages,
            add_datetime_to_instructions=self.django_agent.add_datetime_to_instructions,
            debug_mode=self.django_agent.debug_mode,
            read_tool_call_history=self.django_agent.read_tool_call_history,
            num_history_responses=self.django_agent.num_history_responses,
            # Enable automatic citation tracking
            add_references=True,
        )

        logger.debug(f"[AgentBuilder] Build completed in {time.time() - t0:.2f}s")
        return agent
