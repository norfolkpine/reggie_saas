# apps/reggie/helpers/agent_helpers.py

from typing import Any
import logging

from django.db import connection

from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.knowledge import Knowledge 
from agno.db.postgres.postgres import PostgresDb 
# from agno.models.google import Gemini

from agno.models.groq import Groq
from agno.models.openai import OpenAIChat
from agno.vectordb.pgvector import PgVector
from django.conf import settings
from django.db import connection
from django.db.models import Q
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document
from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters
from llama_index.vector_stores.postgres import PGVectorStore
from pydantic import ConfigDict

from apps.opie.agents.helpers.retrievers import ManualHybridRetriever
from apps.opie.models import Agent as DjangoAgent
from apps.opie.models import AgentInstruction, ModelProvider

logger = logging.getLogger(__name__)


class MultiMetadataAgentKnowledge(Knowledge):
    model_config = ConfigDict(extra="allow")  # Allow extra fields like filter_dict
    
    def __init__(self, vector_db, contents_db=None, num_documents: int = 5, filter_dict: dict[str, str] = None):
        super().__init__(vector_db=vector_db, contents_db=contents_db, num_documents=num_documents)
        self.filter_dict = filter_dict or {}

    def search(self, query: str, num_documents: int = None, **kwargs) -> list[Document]:
        """Override search to include metadata filtering"""
        num_docs = num_documents or self.num_documents

        # Add metadata filters to the search
        if hasattr(self.vector_db, "search_with_filter"):
            return self.vector_db.search_with_filter(query=query, limit=num_docs, filter_dict=self.filter_dict)
        else:
            # No fallback to avoid schema conflicts - return empty results
            logger.warning(f"Vector DB {type(self.vector_db)} does not support search_with_filter, returning empty results")
            return []

    def add_document(self, document: str, metadata: dict[str, Any] = None) -> str:
        """Override to automatically add required metadata"""
        doc_metadata = self.filter_dict.copy()
        if metadata:
            doc_metadata.update(metadata)

        return super().add_document(document, doc_metadata)


class CustomLlamaIndexKnowledge:
    def __init__(self, retriever, filter_dict: dict[str, str] = None, **kwargs):
        self.retriever = retriever
        self.filter_dict = filter_dict or {}
        self.num_documents = kwargs.get('num_documents', 5)

    def search(self, query: str, num_documents: int = None) -> list[Document]:
        """Search using LlamaIndex retriever"""
        try:
            num_docs = num_documents or self.num_documents
            nodes = self.retriever.retrieve(query)
            # Limit results to requested number
            limited_nodes = nodes[:num_docs] if nodes else []
            return [Document(text=node.text, metadata=node.metadata or {}) for node in limited_nodes]
        except Exception as e:
            logger.error(f"Error in LlamaIndex search: {e}")
            return []

    def add_document(self, document: str, metadata: dict[str, Any] = None) -> str:
        """Add document with metadata"""
        doc_metadata = self.filter_dict.copy()
        if metadata:
            doc_metadata.update(metadata)
        
        # For now, return a placeholder ID
        # You may need to implement actual document addition based on your setup
        logger.info(f"Adding document with metadata: {doc_metadata}")
        return f"doc_{hash(document)}"


# Enhanced PgVector class with multi-metadata filtering
class MultiMetadataFilteredPgVector(PgVector):
    def search(self, query: str, limit: int = 5, filters: dict = None, **kwargs) -> list[Document]:
        """Override base search to use our schema-compatible search"""
        filter_dict = filters or {}
        return self.search_with_filter(query=query, filter_dict=filter_dict, limit=limit)

    def search_with_filter(self, query: str, limit: int, filter_dict: dict[str, Any]) -> list[Document]:
        """Search with multiple metadata filters"""
        logger.info(f"Vault search: query='{query}', limit={limit}, filters={filter_dict}")

        embedding = self.embedder.get_embedding(query)

        filter_conditions = []
        params = [embedding]
        for key, value in filter_dict.items():
            # Use metadata_ column for data_vault_vector_table (LlamaIndex format)
            filter_conditions.append("metadata_->>%s = %s")
            params.extend([key, value])
        where_clause = " AND ".join(filter_conditions) if filter_conditions else "1=1"
        params.append(embedding)  # for ORDER BY embedding <=> %s
        params.append(limit)

        # Use correct column names for data_vault_vector_table
        sql = f"""
            SELECT
                text as content,
                metadata_ as metadata,
                1 - (embedding <=> %s::vector) as similarity
            FROM {self.schema}.{self.table_name}
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        logger.info(f"Executing SQL: {sql[:200]}... with params count: {len(params)}")
        logger.info(f"Table: {self.schema}.{self.table_name}, Where clause: {where_clause}")

        from asgiref.sync import sync_to_async
        import asyncio

        def _execute_search():
            results = []
            with connection.cursor() as cursor:
                try:
                    logger.info(f"Executing SQL: {sql}")
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    logger.info(f"Found {len(rows)} documents matching filters")
                    for content, meta_data, _similarity in rows:
                        results.append(Document(text=content, metadata=meta_data))
                except Exception as e:
                    logger.error(f"Error executing search: {e}")
                    return []
            return results

        # Check if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, need to run sync code properly
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_execute_search)
                return future.result()
        except RuntimeError:
            # No running loop, we can execute synchronously
            return _execute_search()


def get_db_url() -> str:
    """Get the database URL from Django settings."""
    if not settings.DATABASE_URL:
        # If DATABASE_URL is not set, construct it from DATABASES settings
        db = settings.DATABASES["default"]
        return f"postgresql://{db['USER']}:{db['PASSWORD']}@{db['HOST']}:{db['PORT']}/{db['NAME']}"
    return settings.DATABASE_URL


def get_schema() -> str:
    """Get the schema name from Django settings, or use default 'ai'."""
    if not hasattr(settings, "AGENT_SCHEMA") or not settings.AGENT_SCHEMA:
        return "ai"
    return settings.AGENT_SCHEMA.strip()


### ====== AGENT INSTRUCTION HANDLING ====== ###


def get_instructions(agent: DjangoAgent, user):
    instructions = []
    excluded_id = None

    if agent.instructions and agent.instructions.is_enabled:
        instructions.append(agent.instructions.instruction)
        excluded_id = agent.instructions.id

    system_global_qs = AgentInstruction.objects.filter(is_enabled=True).filter(Q(is_system=True) | Q(is_global=True))

    if excluded_id:
        system_global_qs = system_global_qs.exclude(id=excluded_id)

    instructions += list(system_global_qs.values_list("instruction", flat=True))

    return instructions


def get_instructions_tuple(agent: DjangoAgent, user):
    user_instruction = None
    excluded_id = None

    if agent.instructions and agent.instructions.is_enabled:
        user_instruction = agent.instructions.instruction
        excluded_id = agent.instructions.id

    other_instructions_qs = AgentInstruction.objects.filter(is_enabled=True).filter(Q(is_system=True))

    if excluded_id:
        other_instructions_qs = other_instructions_qs.exclude(id=excluded_id)

    other_instructions = list(other_instructions_qs.values_list("instruction", flat=True))

    return user_instruction, other_instructions


### ====== AGENT OUTPUT HANDLING ====== ###


def get_expected_output(agent: DjangoAgent) -> str | None:
    if agent.expected_output and agent.expected_output.is_enabled:
        return agent.expected_output.expected_output.strip()
    return None


### ====== MODEL PROVIDER SELECTION ====== ###


def get_llm_model(model_provider: ModelProvider):
    if not model_provider or not model_provider.is_enabled:
        raise ValueError("Agent's assigned model is disabled or missing!")

    model_name = model_provider.model_name
    provider = model_provider.provider

    if provider == "openai":
        return OpenAIChat(id=model_name)
    # elif provider == "google":
    #     return Gemini(id=model_name)
    #    elif provider == "anthropic":
    #        return Claude(id=model_name)
    elif provider == "groq":
        return Groq(id=model_name)
    else:
        raise ValueError(f"Unsupported model provider: {provider}")


def build_agent_database(db_url: str = None) -> PostgresDb:
    return PostgresDb(
        db_url=db_url or get_db_url(),
    )

def build_knowledge_base(
    django_agent: DjangoAgent,
    db_url: str = None,
    schema: str = None,
    top_k: int = 3,
    user=None,  # Full user object for RBAC
    user_uuid: str = None,
    team_id: str = None,
    knowledgebase_id: str = None, 
    project_id: str = None,  
) -> Knowledge | CustomLlamaIndexKnowledge:
    if not django_agent or not django_agent.knowledge_base:
        return
        # raise ValueError("Agent must have a linked KnowledgeBase.")

    if db_url is None:
        db_url = get_db_url()
    if schema is None:
        schema = get_schema()

    print("User uuid: ", user_uuid)
    print("Knowledgebase id: ", knowledgebase_id)

    kb = django_agent.knowledge_base
    table_name = kb.vector_table_name

    # Build metadata filters with RBAC support
    metadata_filters = []
    filter_dict = {}
    
    # Use RBAC service if user is provided
    if user:
        from apps.opie.services.rbac_service import RBACService
        # Get RBAC filters for this user
        rbac_filters = RBACService.get_user_accessible_filters(user)
        
        # If specific knowledgebase_id is provided, check access
        if knowledgebase_id:
            if not RBACService.can_user_access_knowledge_base(user, knowledgebase_id):
                raise ValueError(f"User does not have access to knowledge base {knowledgebase_id}")
        
        # Convert RBAC filters to LlamaIndex format
        # This is a simplified conversion - you may need to enhance based on your needs
        if "$or" in rbac_filters:
            # For OR conditions, we'll use the first matching condition for now
            # (LlamaIndex doesn't directly support OR in the same way)
            for condition in rbac_filters["$or"]:
                if "knowledgebase_id" in condition and knowledgebase_id:
                    if condition["knowledgebase_id"] == knowledgebase_id or \
                       (isinstance(condition["knowledgebase_id"], dict) and 
                        "$in" in condition["knowledgebase_id"] and 
                        knowledgebase_id in condition["knowledgebase_id"]["$in"]):
                        filter_dict.update(condition)
                        break
            else:
                # Use the first available filter
                if rbac_filters["$or"]:
                    filter_dict.update(rbac_filters["$or"][0])
        else:
            filter_dict.update(rbac_filters)
    else:
        # Fallback to basic filtering if no user provided
        # Always required filters - Convert UUIDs to strings
        if user_uuid:
            user_uuid_str = str(user_uuid)  # Convert UUID to string
            metadata_filters.append(MetadataFilter(key="user_uuid", value=user_uuid_str, operator=FilterOperator.EQ))
            filter_dict["user_uuid"] = user_uuid_str

        if team_id:
            team_id_str = str(team_id)  # Convert UUID to string
            metadata_filters.append(MetadataFilter(key="team_id", value=team_id_str, operator=FilterOperator.EQ))
            filter_dict["team_id"] = team_id_str

        # Conditional filters - Convert UUIDs to strings
        if knowledgebase_id:
            knowledgebase_id_str = str(knowledgebase_id)  # Convert UUID to string
            metadata_filters.append(
                MetadataFilter(key="knowledgebase_id", value=knowledgebase_id_str, operator=FilterOperator.EQ)
            )
            filter_dict["knowledgebase_id"] = knowledgebase_id_str

        if project_id:
            project_id_str = str(project_id)  # Convert UUID to string
            metadata_filters.append(MetadataFilter(key="project_id", value=project_id_str, operator=FilterOperator.EQ))
            filter_dict["project_id"] = project_id_str
    
    # Convert filter_dict to metadata_filters for LlamaIndex
    if not metadata_filters and filter_dict:
        for key, value in filter_dict.items():
            if key == "$or" or key == "$and":
                continue  # Skip operators
            if isinstance(value, dict) and "$in" in value:
                # Handle $in operator - use the first value for now
                if value["$in"]:
                    metadata_filters.append(
                        MetadataFilter(key=key, value=str(value["$in"][0]), operator=FilterOperator.EQ)
                    )
            else:
                metadata_filters.append(
                    MetadataFilter(key=key, value=str(value), operator=FilterOperator.EQ)
                )

    if kb.knowledge_type == "agno_pgvector":
        contents_db = PostgresDb(
            db_url=db_url,
            knowledge_table=f"{table_name}_contents",
        )
        vector_db = PgVector(
            db_url=db_url,
            table_name=table_name,
            schema=schema,
            embedder=OpenAIEmbedder(
                id="text-embedding-ada-002",
                dimensions=1536,
            ),
        )
        # Create Knowledge with multi-metadata filtering capability
        if filter_dict:
            return MultiMetadataAgentKnowledge(
                contents_db=contents_db,
                vector_db=vector_db,
                num_documents=top_k,
                filter_dict=filter_dict,
            )
        else:
            return Knowledge(
                contents_db=contents_db,
                vector_db=vector_db,
                num_documents=top_k,
            )

    elif kb.knowledge_type == "llamaindex":
        vector_store = PGVectorStore(
            connection_string=db_url,
            async_connection_string=db_url.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=table_name,
            embed_dim=1536,
            schema_name=schema,
            hybrid_search=True,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

        # Create retrievers with metadata filtering if filters exist
        if metadata_filters:
            # Create combined metadata filter
            combined_filter = MetadataFilters(filters=metadata_filters)

            semantic_retriever = VectorIndexRetriever(index=index, similarity_top_k=top_k, filters=combined_filter)

            # For keyword retriever, you'll need a proper BM25 implementation
            # For now, using semantic retriever with same filter
            keyword_retriever = VectorIndexRetriever(index=index, similarity_top_k=top_k, filters=combined_filter)
        else:
            semantic_retriever = VectorIndexRetriever(index=index, similarity_top_k=top_k)
            keyword_retriever = VectorIndexRetriever(index=index, similarity_top_k=top_k)

        hybrid_retriever = ManualHybridRetriever(
            semantic_retriever=semantic_retriever,
            keyword_retriever=keyword_retriever,
            alpha=0.5,
        )

        return CustomLlamaIndexKnowledge(
            retriever=hybrid_retriever, 
            filter_dict=filter_dict,
            num_documents=top_k
        )

    else:
        raise ValueError(f"Unsupported knowledge base type: {kb.knowledge_type}")
