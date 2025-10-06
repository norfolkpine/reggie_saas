import logging
import os
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime  # ADD THIS
from functools import lru_cache
from typing import Any, Dict, List  # ADD Dict, List, Any to existing

import json
import asyncio
import httpx
import openai

# === Ingest a single GCS file ===
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.gcs import GCSReader
from llama_index.vector_stores.postgres import PGVectorStore
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from tqdm import tqdm


# === Load environment variables early ===
def load_env(secret_id="llamaindex-ingester-env", env_file=".env"):
    """
    Load environment variables:
    - If FORCE_LOCAL_ENV=1, load from .env only.
    - If running in GCP, load from Secret Manager.
    - Else, fallback to .env.
    """
    from dotenv import load_dotenv
    from google.auth.exceptions import DefaultCredentialsError

    # === FORCE LOCAL OVERRIDE ===
    if os.getenv("FORCE_LOCAL_ENV") == "1":
        if load_dotenv(env_file):
            print(f"✅ Forced local: Loaded environment from {env_file}")
        else:
            print(f"⚠️ Forced local: Failed to load {env_file}")
        return

    def is_gcp_environment():
        try:
            import requests

            response = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/",
                headers={"Metadata-Flavor": "Google"},
                timeout=1.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    if is_gcp_environment():
        # Try to load from Secret Manager
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not project_id:
                raise ValueError("GCP_PROJECT or GOOGLE_CLOUD_PROJECT env var not set")
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            env_content = response.payload.data.decode("UTF-8")
            for line in env_content.splitlines():
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value
            print(f"✅ Loaded environment from Secret Manager: {secret_id}")
            return
        except (Exception, DefaultCredentialsError) as e:
            print(f"⚠️ Failed to load from Secret Manager: {e} — falling back to .env")

    # === DEVELOPMENT ===
    if load_dotenv(env_file):
        print(f"✅ Loaded environment from {env_file}")
    else:
        print(f"⚠️ Failed to load {env_file}")


# Call load_env before any config variable reads
load_env()

# === Config Variables ===
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "bh-opie-media")

# Validate required environment variables
if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")

DATABASE_URL = os.getenv("DATABASE_URL")
VECTOR_TABLE_NAME = os.getenv("PGVECTOR_TABLE")

SCHEMA_NAME = os.getenv("PGVECTOR_SCHEMA", "ai")  # Changed default to "ai"
# Unified Vault vector table configuration
VAULT_VECTOR_TABLE = os.getenv("VAULT_PGVECTOR_TABLE", "vault_vector_table")  # Single unified table for all Vault files

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Added for Gemini
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")  # Default, might be provider specific
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))  # TODO: This might need to be dynamic
DJANGO_API_URL = os.getenv("DJANGO_API_URL", "http://localhost:8000")
DJANGO_API_KEY = os.getenv("DJANGO_API_KEY")  # System API key for Cloud Run

# Validate Django API key - required for progress updates
if not DJANGO_API_KEY:
    raise ValueError("DJANGO_API_KEY environment variable is required for progress updates")

# === Logging Setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("llama_index")
logger.setLevel(logging.INFO)

# A simple in-memory cache for idempotency keys.
# In a multi-instance production environment, a distributed cache like Redis or Memcached would be more suitable.
IDEMPOTENCY_KEY_CACHE = {}


@lru_cache(maxsize=1)
def get_vector_store(vector_table_name, current_embed_dim):
    # Async engine
    async_engine = create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )

    return PGVectorStore(
        engine=engine,
        async_engine=async_engine,
        table_name=vector_table_name,
        embed_dim=current_embed_dim,
        schema_name=SCHEMA_NAME,
        perform_setup=True,
    )

# === Utility Functions ===

def download_gcs_file(file_path: str) -> bytes:
    """Download file from Google Cloud Storage"""
    try:
        from google.cloud import storage
        
        # Parse GCS path
        if file_path.startswith("gs://"):
            path_parts = file_path[5:].split("/", 1)
            bucket_name = path_parts[0]
            blob_name = path_parts[1] if len(path_parts) > 1 else ""
        else:
            bucket_name = GCS_BUCKET_NAME
            blob_name = file_path
        
        # Download file
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        return blob.download_as_bytes()
        
    except Exception as e:
        logger.error(f"Failed to download file from GCS: {e}")
        raise

async def generate_embeddings(text_chunks: list) -> dict:
    """Generate embeddings for text chunks using OpenAI"""
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        embeddings = []
        total_tokens = 0
        
        for chunk in text_chunks:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=chunk
            )
            embeddings.append(response.data[0].embedding)
            total_tokens += response.usage.total_tokens
        
        return {
            "embeddings": embeddings,
            "tokens_used": total_tokens
        }
        
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise

async def store_vault_embeddings(project_uuid: str, user_uuid: str, file_id: int, text_chunks: list, embeddings: list, metadata: dict):
    """DEPRECATED: Legacy Agno storage function - now using LlamaIndex native approach"""
    logger.warning("🚨 Deprecated function store_vault_embeddings called - this should use LlamaIndex native storage instead")
    logger.warning("⚠️ Vault embeddings should now be processed through process_vault_file_without_progress function")
    raise NotImplementedError(
        "Legacy Agno storage methods are deprecated. Use process_vault_file_without_progress() "
        "which handles embedding through LlamaIndex native PGVectorStore for proper schema compatibility."
    )

async def ensure_vault_vector_table_exists():
    """Ensure unified Vault vector table exists with LlamaIndex-compatible schema"""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Create schema if it doesn't exist
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))

            # Let LlamaIndex PGVectorStore handle table creation with correct schema
            conn.commit()
            logger.info(f"✅ Schema {SCHEMA_NAME} ready for LlamaIndex vault table creation")

    except Exception as e:
        logger.error(f"Failed to ensure Vault vector table exists: {e}")
        raise

# === FastAPI App ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI app."""
    # Load environment variables
    # load_env(secret_id="llamaindex-ingester-env")
    # load_env()

    # Validate required environment variables for Django communication
    if not DJANGO_API_KEY:
        logger.warning("⚠️ No API key configured - progress updates to Django will fail!")
    else:
        # Test the API key with a health check
        try:
            async with httpx.AsyncClient() as client:
                base_url = DJANGO_API_URL.rstrip("/")
                response = await client.get(
                    f"{base_url}/health/",
                    headers={
                        "Authorization": f"Api-Key {DJANGO_API_KEY}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-Request-Source": "cloud-run-ingestion",
                    },
                    timeout=5.0,
                )

                if response.status_code == 403:
                    logger.warning("⚠️ Django API key authentication failed - progress updates will fail")
                elif response.status_code in [200, 500]:
                    # Accept 500 as it might just mean Celery is down
                    if response.status_code == 500 and "CeleryHealthCheckCelery" in response.text:
                        logger.info(
                            "✅ Django API key validated successfully (Celery is down but authentication worked)"
                        )
                    else:
                        logger.info("✅ Django API key validated successfully")
                else:
                    logger.warning(f"⚠️ Unexpected status code from Django: {response.status_code}")

        except Exception as e:
            logger.warning(f"⚠️ Django API key validation failed: {str(e)}")

    yield

    # Cleanup (if needed)
    logger.info("Shutting down...")


app = FastAPI(lifespan=lifespan)


# === Request Models ===
class IngestRequest(BaseModel):
    gcs_prefix: str
    file_limit: int | None = None
    vector_table_name: str


class FileIngestRequest(BaseModel):
    file_path: str = Field(..., description="Full GCS path to the file")
    vector_table_name: str = Field(..., description="Name of the vector table to store embeddings")
    file_uuid: str = Field(..., description="UUID of the file in Django")
    link_id: int | None = Field(None, description="Optional link ID for tracking specific ingestion")
    embedding_provider: str = Field(..., description="Embedding provider, e.g., 'openai' or 'google'")
    embedding_model: str = Field(
        ..., description="Model to use for embeddings, e.g., 'text-embedding-ada-002' or 'models/embedding-004'"
    )
    chunk_size: int | None = Field(1000, description="Size of text chunks")
    chunk_overlap: int | None = Field(200, description="Overlap between chunks")
    batch_size: int | None = Field(20, description="Number of documents to process in each batch")
    progress_update_frequency: int | None = Field(10, description="Minimum percentage points between progress updates")

    # ===== NEW METADATA FIELDS =====
    # Required metadata fields
    user_uuid: str = Field(..., description="UUID of the user who owns this document")
    team_id: str | None = Field(None, description="ID of the team this document belongs to")

    # Conditional metadata fields
    knowledgebase_id: str | None = Field(None, description="ID of the knowledge base (conditional)")
    project_id: str | None = Field(None, description="ID of the project (conditional)")

    # Additional optional metadata
    custom_metadata: dict[str, Any] | None = Field(None, description="Additional custom metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "gs://your-bucket/path/to/file.pdf",
                "vector_table_name": "your_vector_table",
                "file_uuid": "123e4567-e89b-12d3-a456-426614174000",
                "link_id": 1,
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-ada-002",
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "batch_size": 20,
                "progress_update_frequency": 10,
                # New metadata fields
                "user_uuid": "user_123e4567-e89b-12d3-a456-426614174000",
                # "team_id": "team_987fcdeb-51a2-43d1-9c4e-567890123456",  # Example: optional field
                "knowledgebase_id": "kb_456789ab-cdef-1234-5678-90abcdef1234",
                "project_id": "proj_789abcde-f123-4567-890a-bcdef1234567",
                "custom_metadata": {"department": "engineering", "priority": "high"},
            }
        }

    def clean_file_path(self) -> str:
        """Clean and validate the file path."""
        path = self.file_path

        # Log original path
        logger.info(f"🔍 Original file path: {path}")

        # Check if this is a local file path (starts with /)
        if path.startswith("/"):
            # Local file path - return as-is
            logger.info(f"🔍 Local file path detected: {path}")
            return path

        # Handle gs:// prefix for GCS files
        if path.startswith("gs://"):
            # Split into bucket and path parts
            parts = path[5:].split("/", 1)
            if len(parts) == 2:
                bucket_name, file_path = parts
                # Don't modify the path structure, just ensure no double slashes
                path = f"gs://{bucket_name}/{file_path}"
        else:
            # If no gs:// prefix, add it with the configured bucket
            path = f"gs://{GCS_BUCKET_NAME}/{path}"

        # Log path after gs:// handling
        logger.info(f"🔍 Path after gs:// handling: {path}")

        # Extract bucket and path
        if path.startswith("gs://"):
            parts = path[5:].split("/", 1)
            if len(parts) > 1:
                bucket_name, file_path = parts
                logger.info(f"🔍 Using bucket: {bucket_name}")
                logger.info(f"🔍 Using file path: {file_path}")

        # Remove any double slashes (but preserve gs://)
        if "gs://" in path:
            gs_parts = path.split("gs://", 1)
            path = "gs://" + gs_parts[1].replace("//", "/")
        else:
            path = path.replace("//", "/")

        logger.info(f"🔍 Final cleaned path: {path}")
        return path


class DeleteVectorRequest(BaseModel):
    vector_table_name: str = Field(..., description="Name of the vector table containing the vectors")
    file_uuid: str = Field(..., description="UUID of the file whose vectors should be deleted")


# === Common indexing logic ===
def index_documents(docs, source: str, vector_table_name: str, embed_model):  # Modified to accept embed_model
    if not docs:
        raise HTTPException(status_code=404, detail=f"No documents found for {source}")

    logger.info(
        f"📊 Starting embedding for {len(docs)} documents from source: {source} using {embed_model.__class__.__name__}"
    )
    # embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY) # Removed: embed_model is now passed

    vector_store = PGVectorStore(
        connection_string=DATABASE_URL,
        async_connection_string=DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        table_name=vector_table_name,
        embed_dim=EMBED_DIM,
        schema_name=SCHEMA_NAME,
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info("🧠 Building VectorStoreIndex...")
    VectorStoreIndex.from_documents(
        docs, storage_context=storage_context, embed_model=embed_model
    )  # Use passed embed_model
    logger.info("✅ Embedding and indexing complete.")

    return {"indexed_documents": len(docs), "source": source, "vector_table": vector_table_name}


# === Ingest by GCS prefix (bulk mode) ===
@app.post("/ingest-gcs")
async def ingest_gcs_docs(payload: IngestRequest):
    try:
        logger.info(f"🔎 Starting GCS ingestion for prefix: {payload.gcs_prefix}")
        reader_kwargs = {"bucket": GCS_BUCKET_NAME, "prefix": payload.gcs_prefix}

        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH

        reader = GCSReader(**reader_kwargs)

        resources = reader.list_resources()
        if payload.file_limit:
            resources = resources[: payload.file_limit]
        logger.info(f"📦 Found {len(resources)} resources")

        documents = []
        for name in tqdm(resources, desc="📂 Loading docs"):
            logger.info(f"📄 Loading file: {name}")
            try:
                result = reader.load_resource(name)
                loaded_docs = result if isinstance(result, list) else [result]
                # consider adding custom metadata doc.metadata {}
                documents.extend(loaded_docs)
            except Exception as e:
                logger.warning(f"❌ Failed to load {name}: {str(e)}")

        # For now, /ingest-gcs will default to OpenAI as it doesn't have provider selection yet
        # TODO: Future improvement: Allow provider selection for /ingest-gcs
        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY is not set. Cannot proceed with default GCS ingestion.")
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set for GCS ingestion.")

        default_embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
        logger.info(f"⚠️ /ingest-gcs defaulting to OpenAI embeddings ({EMBEDDING_MODEL}).")
        return index_documents(
            documents,
            source=payload.gcs_prefix,
            vector_table_name=payload.vector_table_name,
            embed_model=default_embedder,
        )

    except Exception as e:
        import traceback

        logger.error(f"❌ Ingestion error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Stage weights for progress calculation
STAGE_WEIGHTS = {
    "download": 0.05,
    "parse": 0.20,
    "chunk": 0.10,
    "embed_index": 0.60,  # Combined embed and index
    "finalize": 0.05,
}


async def process_single_file_stream(payload: FileIngestRequest, idempotency_key: str):
    """
    Processes a single file and streams progress updates as newline-delimited JSON.
    """
    processed_chunks = 0
    total_chunks = 0
    base_progress = 0

    # This is a helper generator to avoid repeating the json.dumps and newline logic
    async def yield_progress_update(status, stage, percent, message, error_detail=None):
        update = {
            "status": status,
            "stage": stage,
            "percent": round(min(percent, 100.0), 2),
            "message": message,
        }
        if error_detail:
            update["error"] = error_detail
        yield json.dumps(update) + "\n"

    try:
        # Initial event to signal start
        await asyncio.sleep(0.01)
        async for update in yield_progress_update("processing", "start", 0, "Starting ingestion"):
            yield update

        # === Stage: Download & Parse ===
        file_path = payload.clean_file_path()
        
        # Check if this is a local file path (starts with /) or GCS path
        if file_path.startswith("/"):
            # Local file path - read directly from filesystem
            logger.info(f"📁 Reading local file: {file_path}")
            if not os.path.exists(file_path):
                raise ValueError(f"Local file does not exist: {file_path}")
            
            # Use SimpleDirectoryReader for local files
            from llama_index.core import SimpleDirectoryReader
            reader = SimpleDirectoryReader(input_files=[file_path])
            result = reader.load_data()
        else:
            # GCS file path - use existing GCS logic
            if not GCS_BUCKET_NAME:
                raise ValueError("GCS_BUCKET_NAME is not configured")

            if file_path.startswith("gs://"):
                parts = file_path[5:].split("/", 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid GCS path format: {file_path}")
                bucket_name, actual_path = parts
                if bucket_name != GCS_BUCKET_NAME:
                    raise ValueError(f"File is in bucket {bucket_name} but service is configured for {GCS_BUCKET_NAME}")
                file_path = actual_path

            reader_kwargs = {"bucket": GCS_BUCKET_NAME, "key": file_path}
            if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
                reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH
            reader = GCSReader(**reader_kwargs)

            try:
                result = reader.load_data()
            except Exception as e:
                raise ValueError(f"Failed to read file {file_path} from GCS: {str(e)}")

        documents = result if isinstance(result, list) else [result]
        if not documents or not documents[0].text.strip():
            raise ValueError(f"No content could be extracted from file: {file_path}")

        base_progress = STAGE_WEIGHTS["download"] + STAGE_WEIGHTS["parse"]
        async for update in yield_progress_update("processing", "parse", base_progress * 100, f"Parsed {len(documents)} documents"):
            yield update

        # === Stage: Setup Embedder & Vector Store ===
        embedder = None
        current_embed_dim = EMBED_DIM
        if payload.embedding_provider == "openai":
            if not OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is not configured.")
            embedder = OpenAIEmbedding(model=payload.embedding_model, api_key=OPENAI_API_KEY)
            if hasattr(embedder, "dimensions") and embedder.dimensions:
                current_embed_dim = embedder.dimensions
        elif payload.embedding_provider == "google":
            # Simplified for brevity
            embedder = GeminiEmbedding(model_name=payload.embedding_model)
            if "embedding-004" in payload.embedding_model:
                current_embed_dim = 768
        else:
            raise ValueError(f"Unsupported embedding provider: {payload.embedding_provider}")

        vector_store = get_vector_store(payload.vector_table_name, current_embed_dim)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # === Stage: Chunking ===
        text_splitter = TokenTextSplitter(chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap)
        base_metadata = {
            "file_uuid": payload.file_uuid,
            "user_uuid": payload.user_uuid,
            "ingested_at": datetime.now().isoformat(),
        }
        if payload.team_id: base_metadata["team_id"] = payload.team_id
        if payload.knowledgebase_id: base_metadata["knowledgebase_id"] = payload.knowledgebase_id
        if payload.project_id: base_metadata["project_id"] = payload.project_id
        if payload.link_id: base_metadata["link_id"] = str(payload.link_id)
        if payload.custom_metadata: base_metadata.update(payload.custom_metadata)
        
        all_chunks = []
        for doc in documents:
            text_chunks = text_splitter.split_text(doc.text or "")
            doc_metadata = base_metadata.copy()
            doc_metadata.update(doc.metadata or {})
            all_chunks.extend([Document(text=chunk, metadata=doc_metadata) for chunk in text_chunks if chunk.strip()])

        total_chunks = len(all_chunks)
        if total_chunks == 0:
            raise ValueError("File yielded no text chunks to process.")

        base_progress += STAGE_WEIGHTS["chunk"]
        async for update in yield_progress_update("processing", "chunk", base_progress * 100, f"Created {total_chunks} text chunks"):
            yield update

        # === Stage: Embed & Index ===
        batch_size = payload.batch_size or 20
        for i in range(0, total_chunks, batch_size):
            batch_chunks = all_chunks[i:i + batch_size]
            VectorStoreIndex.from_documents(batch_chunks, storage_context=storage_context, embed_model=embedder)

            processed_chunks += len(batch_chunks)
            chunk_progress = processed_chunks / total_chunks if total_chunks > 0 else 1
            current_stage_progress = STAGE_WEIGHTS["embed_index"] * chunk_progress
            total_percent = (base_progress + current_stage_progress) * 100

            await asyncio.sleep(0.01)  # Yield control to prevent event loop blocking
            async for update in yield_progress_update("processing", "embed_index", total_percent, f"Indexed {processed_chunks}/{total_chunks} chunks"):
                yield update

        # === Stage: Finalize ===
        IDEMPOTENCY_KEY_CACHE[idempotency_key] = {"status": "completed"}
        logger.info(f"✅ Successfully processed file for idempotency key: {idempotency_key}")
        async for update in yield_progress_update("completed", "finalize", 100, "Ingestion complete"):
            yield update

    except Exception as e:
        error_message = f"Ingestion failed: {str(e)}"
        logger.error(f"❌ {error_message}", exc_info=True)
        IDEMPOTENCY_KEY_CACHE[idempotency_key] = {"status": "failed", "error": error_message}
        # Calculate actual progress when error occurred instead of hardcoding 100%
        current_progress = 0
        if 'base_progress' in locals():
            current_progress = base_progress * 100
        elif 'total_chunks' in locals() and 'processed_chunks' in locals() and total_chunks > 0:
            chunk_progress = processed_chunks / total_chunks
            current_progress = (STAGE_WEIGHTS["download"] + STAGE_WEIGHTS["parse"] + STAGE_WEIGHTS["chunk"] + STAGE_WEIGHTS["embed_index"] * chunk_progress) * 100
        async for update in yield_progress_update("failed", "error", current_progress, "Ingestion failed", error_detail=error_message):
            yield update


@app.post("/ingest-file")
async def ingest_single_file(request: Request, payload: FileIngestRequest):
    """
    Handles a file ingestion request, supporting idempotency and streaming progress.
    """
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required.")

    cached_result = IDEMPOTENCY_KEY_CACHE.get(idempotency_key)
    if cached_result:
        status = cached_result.get("status")
        logger.info(f"Idempotency key {idempotency_key} already in cache with status '{status}'.")

        if status == "processing":
            raise HTTPException(status_code=409, detail=f"Ingestion for key {idempotency_key} is already in progress.")

        async def cached_streamer():
            """Streams the final, cached result back to the client."""
            final_message = {
                "status": status,
                "stage": "finalize",
                "percent": 100.0,
                "message": f"Request with this key was already processed with status: {status}",
            }
            if status == "failed":
                final_message["error"] = cached_result.get("error", "An unknown error occurred.")
            yield json.dumps(final_message) + "\n"

        return StreamingResponse(cached_streamer(), media_type="application/x-ndjson")

    IDEMPOTENCY_KEY_CACHE[idempotency_key] = {"status": "processing"}
    return StreamingResponse(process_single_file_stream(payload, idempotency_key), media_type="application/x-ndjson")


# === Delete vectors for a file ===
@app.post("/delete-vectors")
async def delete_vectors(payload: DeleteVectorRequest):
    try:
        logger.info(f"🗑️ Deleting vectors for file: {payload.file_uuid}")

        # Initialize vector store
        vector_store = PGVectorStore(
            connection_string=DATABASE_URL,
            async_connection_string=DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=payload.vector_table_name,
            embed_dim=EMBED_DIM,
            schema_name=SCHEMA_NAME,
        )

        # Delete vectors with matching file_uuid in metadata
        # Use the delete_by_metadata method if available, otherwise use delete with ref_doc_id
        try:
            # Try the filter_dict approach first
            deleted_count = vector_store.delete(filter_dict={"file_uuid": payload.file_uuid})
        except TypeError as e:
            if "missing 1 required positional argument: 'ref_doc_id'" in str(e):
                # Fallback: delete by ref_doc_id (using file_uuid as ref_doc_id)
                deleted_count = vector_store.delete(ref_doc_id=payload.file_uuid)
            else:
                raise

        logger.info(f"✅ Successfully deleted {deleted_count} vectors")
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "file_uuid": payload.file_uuid,
            "vector_table": payload.vector_table_name,
        }

    except Exception as e:
        logger.error(f"❌ Error deleting vectors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e

async def download_file_from_gcs(bucket_name: str, file_path: str) -> bytes:
    """Download file from Google Cloud Storage"""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        # Download file content
        content = blob.download_as_bytes()
        logger.info(f"✅ Downloaded {len(content)} bytes from gs://{bucket_name}/{file_path}")
        return content
        
    except Exception as e:
        logger.error(f"❌ Failed to download file from GCS: {e}")
        raise

# === Vector Storage Functions ===

async def get_database_connection():
    """Get PostgreSQL database connection"""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        # Get database URL from environment
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        return SessionLocal(), engine
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        raise

async def ensure_vector_table_exists(table_name: str):
    """Create vector table if it doesn't exist"""
    try:
        session, engine = await get_database_connection()
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR(1536),  -- OpenAI text-embedding-3-small dimension
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_id, chunk_index)
        );
        
        CREATE INDEX IF NOT EXISTS {table_name}_embedding_idx 
        ON {table_name} USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100);
        
        CREATE INDEX IF NOT EXISTS {table_name}_file_id_idx 
        ON {table_name} (file_id);
        """
        
        with engine.connect() as connection:
            connection.execute(text(create_table_sql))
            connection.commit()
        
        session.close()
        logger.info(f"✅ Vector table {table_name} ready")
        
    except Exception as e:
        logger.error(f"❌ Failed to create vector table {table_name}: {e}")
        raise

async def store_embeddings(
    table_name: str, 
    file_id: int, 
    chunks: List[str], 
    embeddings: List[List[float]],
    metadata: Dict = None
):
    """Store text chunks and embeddings in vector database"""
    try:
        session, engine = await get_database_connection()
        
        # Delete existing embeddings for this file
        delete_sql = f"DELETE FROM {table_name} WHERE file_id = :file_id"
        with engine.connect() as connection:
            connection.execute(text(delete_sql), {"file_id": file_id})
            connection.commit()
        
        # Insert new embeddings
        insert_sql = f"""
        INSERT INTO {table_name} (file_id, chunk_index, content, embedding, metadata)
        VALUES (:file_id, :chunk_index, :content, :embedding, :metadata)
        """
        
        with engine.connect() as connection:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                connection.execute(text(insert_sql), {
                    "file_id": file_id,
                    "chunk_index": i,
                    "content": chunk,
                    "embedding": embedding,
                    "metadata": metadata or {}
                })
            connection.commit()
        
        session.close()
        logger.info(f"✅ Stored {len(chunks)} chunks for file {file_id} in {table_name}")
        
    except Exception as e:
        logger.error(f"❌ Failed to store embeddings: {e}")
        raise

# === Healthcheck route (for Cloud Run probe) ===
@app.get("/")
async def root():
    return {"message": "LlamaIndex GCS ingestion service is alive!"}


# === Run server locally (for dev) ===
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)