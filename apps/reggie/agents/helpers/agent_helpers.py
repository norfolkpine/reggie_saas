# apps/reggie/helpers/agent_helpers.py

from typing import Any, Dict, List, Optional, Union

from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge import AgentKnowledge
from agno.knowledge.llamaindex import LlamaIndexKnowledgeBase
from agno.memory import AgentMemory
from agno.memory.db.postgres import PgMemoryDb

# from agno.models.anthropic import Claude
from agno.models.google import Gemini
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

from apps.reggie.agents.helpers.retrievers import ManualHybridRetriever
from apps.reggie.models import Agent as DjangoAgent
from apps.reggie.models import AgentInstruction, ModelProvider


class MultiMetadataAgentKnowledge(AgentKnowledge):
    def __init__(self, vector_db, num_documents: int, filter_dict: Dict[str, str]):
        super().__init__(vector_db=vector_db, num_documents=num_documents)
        self.filter_dict = filter_dict

    def search(self, query: str, num_documents: int = None) -> List[Document]:
        """Override search to include metadata filtering"""
        num_docs = num_documents or self.num_documents

        # Add metadata filters to the search
        if hasattr(self.vector_db, "search_with_filter"):
            return self.vector_db.search_with_filter(query=query, limit=num_docs, filter_dict=self.filter_dict)
        else:
            # Fallback: search all and filter in Python (less efficient)
            all_results = super().search(query, num_docs * 5)  # Get more results
            filtered_results = []

            for doc in all_results:
                match = True
                for key, value in self.filter_dict.items():
                    if doc.metadata.get(key) != value:
                        match = False
                        break
                if match:
                    filtered_results.append(doc)

            return filtered_results[:num_docs]

    def add_document(self, document: str, metadata: Dict[str, Any] = None) -> str:
        """Override to automatically add required metadata"""
        doc_metadata = self.filter_dict.copy()
        if metadata:
            doc_metadata.update(metadata)

        return super().add_document(document, doc_metadata)


class MultiMetadataLlamaIndexKnowledgeBase(LlamaIndexKnowledgeBase):
    model_config = ConfigDict(extra="allow")  # Allow extra fields

    def __init__(self, retriever, filter_dict: Dict[str, str] = None, **kwargs):
        super().__init__(retriever=retriever, **kwargs)
        self.filter_dict = filter_dict or {}

    def add_document(self, document: str, metadata: Dict[str, Any] = None) -> str:
        """Override to automatically add required metadata"""
        doc_metadata = self.filter_dict.copy()
        if metadata:
            doc_metadata.update(metadata)
        return super().add_document(document, doc_metadata)


# Enhanced PgVector class with multi-metadata filtering
class MultiMetadataFilteredPgVector(PgVector):
    def search_with_filter(self, query: str, limit: int, filter_dict: Dict[str, Any]) -> List[Document]:
        """Search with multiple metadata filters"""

        embedding = self.embedder.get_embedding(query)

        filter_conditions = []
        params = [embedding]
        for key, value in filter_dict.items():
            filter_conditions.append("metadata->>%s = %s")
            params.extend([key, value])
        where_clause = " AND ".join(filter_conditions) if filter_conditions else "1=1"
        params.append(embedding)  # for ORDER BY embedding <=> %s
        params.append(limit)

        sql = f"""
            SELECT content, metadata, 1 - (embedding <=> %s) as similarity
            FROM {self.table_name}
            WHERE {where_clause}
            ORDER BY embedding <=> %s
            LIMIT %s
        """

        results = []
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            for content, metadata, similarity in cursor.fetchall():
                results.append(Document(content=content, metadata=metadata))
        return results


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


def get_expected_output(agent: DjangoAgent) -> Optional[str]:
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
    elif provider == "google":
        return Gemini(id=model_name)
    #    elif provider == "anthropic":
    #        return Claude(id=model_name)
    elif provider == "groq":
        return Groq(id=model_name)
    else:
        raise ValueError(f"Unsupported model provider: {provider}")


### ====== MEMORY DB BUILD ====== ###


def build_agent_memory(table_name: str) -> AgentMemory:
    return AgentMemory(
        db=PgMemoryDb(table_name=table_name, db_url=get_db_url()),
        create_user_memories=True,
        create_session_summary=True,
    )


### ====== KNOWLEDGE BASE BUILD (Dynamic) ====== ###


def build_knowledge_base(
    django_agent: DjangoAgent,
    db_url: str = get_db_url(),
    schema: str = "ai",
    top_k: int = 3,
    user_uuid: str = None,
    team_id: str = None,
    knowledgebase_id: str = None,  # Conditional
    project_id: str = None,  # Conditional
) -> Union[AgentKnowledge, LlamaIndexKnowledgeBase]:
    if not django_agent or not django_agent.knowledge_base:
        raise ValueError("Agent must have a linked KnowledgeBase.")

    print("User uuid: ", user_uuid)
    print("Knowledgebase id: ", knowledgebase_id)

    kb = django_agent.knowledge_base
    table_name = kb.vector_table_name

    # Build metadata filters
    metadata_filters = []
    filter_dict = {}

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

    if kb.knowledge_type == "agno_pgvector":
        # Create PgVector with user filtering capability
        vector_db = PgVector(
            db_url=db_url,
            table_name=table_name,
            schema=schema,
            embedder=OpenAIEmbedder(
                id="text-embedding-ada-002",
                dimensions=1536,
            ),
            hybrid_search=True,
        )

        # Create AgentKnowledge with multi-metadata filtering capability
        if metadata_filters:
            return MultiMetadataAgentKnowledge(
                vector_db=vector_db,
                num_documents=top_k,
                filter_dict=filter_dict,
            )
        else:
            return AgentKnowledge(
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

        return MultiMetadataLlamaIndexKnowledgeBase(retriever=hybrid_retriever, filter_dict=filter_dict)

    else:
        raise ValueError(f"Unsupported knowledge base type: {kb.knowledge_type}")
