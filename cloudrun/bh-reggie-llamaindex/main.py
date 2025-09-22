import logging
import os
import urllib.parse
import tempfile
import asyncio
import time
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Any, List, Dict, Optional
from io import BytesIO
import openai

import httpx

# Text extraction libraries
# Vault processing now uses unified LlamaIndex service for all file types
try:
    import PyPDF2
    from docx import Document as DocxDocument
    from pptx import Presentation
    import openpyxl
    import tiktoken
    PDF_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some text extraction libraries not available: {e}")
    PDF_AVAILABLE = False

# === Ingest a single GCS file ===
from fastapi import FastAPI, HTTPException
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.gcs import GCSReader
from llama_index.vector_stores.postgres import PGVectorStore
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
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
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "bh-reggie-media")

# Validate required environment variables
if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")

POSTGRES_URL = os.getenv("POSTGRES_URL")
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


# Create settings object for progress updates
class Settings:
    DJANGO_API_URL = DJANGO_API_URL
    DJANGO_API_KEY = DJANGO_API_KEY
    API_PREFIX = "reggie/api/v1"  # Include reggie prefix for correct URL routing

    @property
    def auth_headers(self):
        """Return properly formatted auth headers for system API key."""
        if not self.DJANGO_API_KEY:
            logger.error("❌ No API key configured - progress updates will fail!")
            raise HTTPException(
                status_code=500,
                detail="Django API key is required for progress updates. Ingestion will continue but progress won't be tracked.",
            ) from None

        # Log the header being used (with masked key)
        masked_key = f"{self.DJANGO_API_KEY[:4]}...{self.DJANGO_API_KEY[-4:]}"
        logger.info(f"🔑 Using System API Key: {masked_key}")

        return {
            "Authorization": f"Api-Key {self.DJANGO_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-Source": "cloud-run-ingestion",
        }

    def update_file_progress_sync(
        self,
        file_uuid: str,
        progress: float,
        processed_docs: int,
        total_docs: int,
        link_id: int | None = None,
        error: str | None = None,
    ):
        """Update file ingestion progress."""
        try:
            with httpx.Client() as client:
                # Remove trailing slash from base URL and ensure API_PREFIX doesn't start with slash
                base_url = self.DJANGO_API_URL.rstrip("/")
                api_prefix = self.API_PREFIX.lstrip("/")
                url = f"{base_url}/{api_prefix}/files/{file_uuid}/update-progress/"

                # Ensure progress is between 0 and 100
                progress = min(max(progress, 0), 100)

                data = {
                    "progress": round(progress, 2),  # Round to 2 decimal places
                    "processed_docs": processed_docs,
                    "total_docs": total_docs,
                }

                # Only include link_id if it's provided and valid
                if link_id is not None and link_id > 0:
                    data["link_id"] = link_id

                if error:
                    data["error"] = error

                response = client.post(url, headers=self.auth_headers, json=data, timeout=10.0)
                self.validate_auth_response(response)

                # Log different messages based on progress
                if progress >= 100:
                    logger.info(f"✅ Ingestion completed: {processed_docs}/{total_docs} documents")
                else:
                    logger.info(f"📊 Progress updated: {progress:.1f}% ({processed_docs}/{total_docs})")

                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Failed to update progress: {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to update progress: {str(e)}")
            raise

    def validate_auth_response(self, response):
        """Validate authentication response and log helpful messages."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.error("❌ Authentication failed - invalid or revoked API key")
                logger.error(f"Response body: {e.response.text}")
                # Re-raise with more helpful message
                raise HTTPException(
                    status_code=403,
                    detail="Authentication failed. Please ensure your system API key is valid and not revoked.",
                )
            raise


settings = Settings()


@lru_cache(maxsize=1)
def get_vector_store(vector_table_name, current_embed_dim):
    # Async engine
    async_engine = create_async_engine(
        POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )
    engine = create_engine(
        POSTGRES_URL,
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

        engine = create_engine(POSTGRES_URL)

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
        logger.info(f"✅ Django API key configured for {DJANGO_API_URL}")
        # Skip health check during startup to avoid hanging
        # The health check can be done during actual API calls if needed

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

        # Handle gs:// prefix
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
        connection_string=POSTGRES_URL,
        async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
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


@app.post("/ingest-file")
def ingest_single_file(payload: FileIngestRequest):
    logger.info(f"📄 Queuing ingestion for file: {payload.file_path}")
    process_single_file(payload)
    return {"status": "queued", "file_path": payload.file_path}


def process_single_file(payload: FileIngestRequest):
    try:
        logger.info(f"📄 Ingesting single file: {payload.file_path}")

        # Step 1: Clean and validate file path
        file_path = payload.clean_file_path()

        if not GCS_BUCKET_NAME:
            raise ValueError("GCS_BUCKET_NAME is not configured")

        logger.info(f"🔍 Using cleaned path: {file_path}")
        logger.info(f"🔍 Using GCS bucket: {GCS_BUCKET_NAME}")

        # Extract the actual file path from the GCS URL
        if file_path.startswith("gs://"):
            parts = file_path[5:].split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid GCS path format: {file_path}")
            bucket_name, actual_path = parts
            if bucket_name != GCS_BUCKET_NAME:
                raise ValueError(f"File is in bucket {bucket_name} but service is configured for {GCS_BUCKET_NAME}")
            file_path = actual_path

        # Step 2: Reading file with GCS Reader
        reader_kwargs = {
            "bucket": GCS_BUCKET_NAME,
            "key": file_path,
        }

        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH
            logger.info(f"📚 Using credentials from: {CREDENTIALS_PATH}")

        logger.info(f"📚 Initializing GCS reader with bucket: {GCS_BUCKET_NAME}, key: {file_path}")
        reader = GCSReader(**reader_kwargs)

        try:
            # Try to load the data
            logger.info(f"📚 Attempting to load file from bucket: {GCS_BUCKET_NAME}")
            logger.info(f"📚 Using file path: {file_path}")
            result = reader.load_data()

            if not result:
                # If that fails, try with URL-decoded path
                decoded_path = urllib.parse.unquote(file_path)
                if decoded_path != file_path:
                    logger.info(f"📚 First attempt failed. Retrying with decoded path: {decoded_path}")
                    reader_kwargs["key"] = decoded_path
                    reader = GCSReader(**reader_kwargs)
                    result = reader.load_data()

            if not result:
                error_msg = f"No content loaded from file after multiple attempts. Path tried: {file_path}"
                if "decoded_path" in locals():
                    error_msg += f", {decoded_path}"
                logger.error(error_msg)
                raise ValueError(error_msg)

        except Exception as e:
            error_msg = f"❌ Failed to read file {file_path} from bucket {GCS_BUCKET_NAME}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Reader kwargs: {reader_kwargs}")
            logger.error(f"Original file path: {payload.file_path}")
            logger.error(f"Cleaned file path: {file_path}")

            # Update progress to failed state if we have link_id
            if payload.link_id:
                try:
                    settings.update_file_progress_sync(
                        file_uuid=payload.file_uuid,
                        progress=0,
                        processed_docs=0,
                        total_docs=0,
                        link_id=payload.link_id,
                        error=error_msg,
                    )
                except Exception as progress_e:
                    logger.error(f"Failed to update progress after file read error: {progress_e}")
            raise HTTPException(status_code=500, detail=error_msg)

        documents = result if isinstance(result, list) else [result]
        total_docs = len(documents)
        if total_docs == 0:
            raise HTTPException(status_code=400, detail=f"No documents extracted from file: {file_path}")

        logger.info(f"📄 Processing {total_docs} documents from file")
        processed_docs = 0

        # Send initial progress update
        settings.update_file_progress_sync(
            file_uuid=payload.file_uuid, progress=0, processed_docs=0, total_docs=total_docs, link_id=payload.link_id
        )

        # === Dynamic Embedder Instantiation ===
        embedder = None
        current_embed_dim = EMBED_DIM  # Default, will try to update based on model
        logger.info(f"Requested embedding provider: {payload.embedding_provider}, model: {payload.embedding_model}")

        if payload.embedding_provider == "openai":
            if not OPENAI_API_KEY:
                raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
            embedder = OpenAIEmbedding(model=payload.embedding_model, api_key=OPENAI_API_KEY)
            if hasattr(embedder, "dimensions") and embedder.dimensions:
                current_embed_dim = embedder.dimensions
            else:
                logger.warning(
                    f"Could not determine dimensions for OpenAI model {payload.embedding_model}. Falling back to default EMBED_DIM={EMBED_DIM}."
                )
        elif payload.embedding_provider == "google":
            if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                logger.warning(
                    "Neither GOOGLE_API_KEY nor GOOGLE_APPLICATION_CREDENTIALS is set. Gemini Embedding might fail."
                )

            try:
                embedder = GeminiEmbedding(model_name=payload.embedding_model)
                # Attempt to get dimensions. This is a bit of a guess for Gemini.
                # LlamaIndex's GeminiEmbedding might not have a direct 'dimensions' attribute.
                # We might need a mapping for known models.
                # Example: "models/embedding-004" is 768.
                # model_name for GeminiEmbedding is like "models/embedding-001"
                if (
                    "embedding-004" in payload.embedding_model or "embedding-001" in payload.embedding_model
                ):  # Newer model
                    current_embed_dim = 768
                # Add more known models here or find a programmatic way if available
                else:
                    # If model is unknown, try to get from a 'dimensions' attribute if it exists (speculative)
                    if hasattr(embedder, "dimensions") and embedder.dimensions:
                        current_embed_dim = embedder.dimensions
                    else:
                        logger.warning(
                            f"Cannot determine dimension for Google model {payload.embedding_model}. Using default {EMBED_DIM}. This might be incorrect."
                        )

            except Exception as e:
                logger.error(f"Failed to initialize GeminiEmbedding: {str(e)}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to initialize Google Gemini Embedding: {str(e)}"
                ) from e
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported embedding provider: {payload.embedding_provider}")

        if embedder is None:
            raise HTTPException(status_code=500, detail="Failed to initialize embedder.")

        logger.info(f"✅ Initialized embedder: {embedder.__class__.__name__} with model {payload.embedding_model}")
        logger.info(f"✅ Using embedding dimension: {current_embed_dim} for vector store.")

        print("payload.vector_table_name", payload.vector_table_name)

        # Create vector store with tested dimension
        vector_store = get_vector_store(payload.vector_table_name, current_embed_dim)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # SIMPLIFIED METADATA (just the essentials)
        base_metadata = {
            "file_uuid": payload.file_uuid,
            "user_uuid": payload.user_uuid,
            "ingested_at": datetime.now().isoformat(),
        }

        # Add optional fields if they exist
        if payload.team_id:
            base_metadata["team_id"] = payload.team_id
            base_metadata["access_level"] = "team"  # Mark as team-accessible
        else:
            base_metadata["access_level"] = "user"  # Mark as user-only
            
        if payload.knowledgebase_id:
            base_metadata["knowledgebase_id"] = payload.knowledgebase_id
        if payload.project_id:
            base_metadata["project_id"] = payload.project_id
        if payload.link_id:
            base_metadata["link_id"] = str(payload.link_id)
        
        # Add any custom metadata if provided
        if payload.custom_metadata:
            for key, value in payload.custom_metadata.items():
                if key not in base_metadata:  # Don't override core metadata
                    base_metadata[key] = value

        # Process documents with your working pattern
        text_splitter = TokenTextSplitter(chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap)
        batch_size = payload.batch_size
        processed_docs = 0

        try:
            for i in range(0, total_docs, batch_size):
                batch = documents[i : i + batch_size]
                chunked_docs = []

                for doc in batch:
                    # Ensure document has content
                    if not doc.text or not doc.text.strip():
                        continue

                    text_chunks = text_splitter.split_text(doc.text)

                    # Combine your base metadata with any existing doc metadata
                    doc_metadata = base_metadata.copy()
                    if doc.metadata:
                        # Add original metadata but keep base_metadata as priority
                        for key, value in doc.metadata.items():
                            if key not in doc_metadata:  # Don't override base metadata
                                doc_metadata[key] = value

                    # YOUR WORKING PATTERN: Simple list comprehension
                    batch_chunks = [
                        Document(text=chunk, metadata=doc_metadata) for chunk in text_chunks if chunk.strip()
                    ]

                    chunked_docs.extend(batch_chunks)

                # Debug batch info
                logger.info(f"📋 Batch {i // batch_size + 1}: {len(chunked_docs)} chunks")

                if chunked_docs:  # Only process if we have chunks
                    # Index the chunked documents
                    VectorStoreIndex.from_documents(chunked_docs, storage_context=storage_context, embed_model=embedder)

                    processed_docs += len(batch)
                    progress = (processed_docs / total_docs) * 100

                    # Update progress
                    settings.update_file_progress_sync(
                        file_uuid=payload.file_uuid,
                        progress=progress,
                        processed_docs=processed_docs,
                        total_docs=total_docs,
                        link_id=payload.link_id,
                    )

                    logger.info(f"✅ Batch {i // batch_size + 1} completed. Progress: {progress:.1f}%")
                else:
                    logger.warning(f"⚠️ Batch {i // batch_size + 1} had no valid chunks")
                    if payload.link_id:
                        try:
                            settings.update_file_progress_sync(
                                file_uuid=payload.file_uuid,
                                progress=progress,  # Keep the last progress
                                processed_docs=processed_docs,
                                total_docs=total_docs,
                                link_id=payload.link_id,
                            )
                        except Exception as progress_e:
                            logger.error(f"Failed to update progress after batch error: {progress_e}")
                    raise HTTPException(
                        status_code=500, detail="Failed to process documents: batch had no valid chunks"
                    ) from None

            # Final progress update
            settings.update_file_progress_sync(
                file_uuid=payload.file_uuid,
                progress=100,
                processed_docs=total_docs,
                total_docs=total_docs,
                link_id=payload.link_id,
            )

            logger.info(f"✅ Successfully processed {total_docs} documents")
            return {
                "status": "completed",
                "message": f"Successfully processed {total_docs} documents",
                "total_docs": total_docs,
                "file_path": file_path,
                "embedding_dimension": current_embed_dim,
            }

        except Exception as e:
            logger.error(f"❌ Error during batch processing: {str(e)}")
            if payload.link_id:
                try:
                    settings.update_file_progress_sync(
                        file_uuid=payload.file_uuid,
                        progress=progress if "progress" in locals() else 0,
                        processed_docs=processed_docs,
                        total_docs=total_docs,
                        link_id=payload.link_id,
                    )
                except Exception as progress_e:
                    logger.error(f"Failed to update progress after processing error: {progress_e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error ingesting file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# === Delete vectors for a file ===
@app.post("/delete-vectors")
async def delete_vectors(payload: DeleteVectorRequest):
    try:
        logger.info(f"🗑️ Deleting vectors for file: {payload.file_uuid}")

        # Initialize vector store
        vector_store = PGVectorStore(
            connection_string=POSTGRES_URL,
            async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=payload.vector_table_name,
            embed_dim=EMBED_DIM,
            schema_name=SCHEMA_NAME,
        )

        # Delete vectors with matching file_uuid in metadata
        deleted_count = vector_store.delete(filter_dict={"file_uuid": payload.file_uuid})

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
        database_url = os.getenv("POSTGRES_URL")
        if not database_url:
            raise ValueError("POSTGRES_URL environment variable not set")
        
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
