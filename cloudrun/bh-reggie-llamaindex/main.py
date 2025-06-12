import logging
import os
import urllib.parse
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.gcs import GCSReader
from llama_index.vector_stores.postgres import PGVectorStore
from pydantic import BaseModel, Field
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
SCHEMA_NAME = os.getenv("PGVECTOR_SCHEMA", "public")
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
            )

        # Log the header being used (with masked key)
        masked_key = f"{self.DJANGO_API_KEY[:4]}...{self.DJANGO_API_KEY[-4:]}"
        logger.info(f"🔑 Using System API Key: {masked_key}")

        return {
            "Authorization": f"Api-Key {self.DJANGO_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-Source": "cloud-run-ingestion",
        }

    async def update_file_progress(
        self,
        file_uuid: str,
        progress: float,
        processed_docs: int,
        total_docs: int,
        link_id: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """Update file ingestion progress."""
        try:
            async with httpx.AsyncClient() as client:
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

                response = await client.post(url, headers=self.auth_headers, json=data, timeout=10.0)
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


# === FastAPI App ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI app."""
    logger.info("🚀 Application startup...")

    # Initialize Embedders
    # OpenAI
    if OPENAI_API_KEY:
        try:
            app.state.openai_embedder = OpenAIEmbedding(api_key=OPENAI_API_KEY)
            logger.info("✅ OpenAI embedder initialized.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize OpenAI embedder: {e}")
            app.state.openai_embedder = None
    else:
        logger.warning("⚠️ OPENAI_API_KEY not found. OpenAI embedder will not be available.")
        app.state.openai_embedder = None

    # Gemini
    # GeminiEmbedding uses GOOGLE_API_KEY from env if not passed directly to constructor
    # Ensure GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS is set.
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            # We don't specify model_name here, it will be set per-request
            app.state.gemini_embedder_client = GeminiEmbedding() # This will be a base client
            logger.info("✅ Google Gemini embedder base client initialized.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Gemini embedder client: {e}")
            app.state.gemini_embedder_client = None
    else:
        logger.warning(
            "⚠️ Neither GOOGLE_API_KEY nor GOOGLE_APPLICATION_CREDENTIALS found. "
            "Google Gemini embedder will not be available."
        )
        app.state.gemini_embedder_client = None


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
    logger.info("Application shutdown...")


app = FastAPI(lifespan=lifespan)


# === Request Models ===
class IngestRequest(BaseModel):
    gcs_prefix: str
    file_limit: Optional[int] = None
    vector_table_name: str


class FileIngestRequest(BaseModel):
    file_path: str = Field(..., description="Full GCS path to the file")
    vector_table_name: str = Field(..., description="Name of the vector table to store embeddings")
    file_uuid: str = Field(..., description="UUID of the file in Django")
    link_id: Optional[int] = Field(None, description="Optional link ID for tracking specific ingestion")
    embedding_provider: str = Field(..., description="Embedding provider, e.g., 'openai' or 'google'")
    embedding_model: str = Field(
        ..., description="Model to use for embeddings, e.g., 'text-embedding-ada-002' or 'models/embedding-004'"
    )
    chunk_size: Optional[int] = Field(1000, description="Size of text chunks")
    chunk_overlap: Optional[int] = Field(200, description="Overlap between chunks")
    batch_size: Optional[int] = Field(20, description="Number of documents to process in each batch")
    progress_update_frequency: Optional[int] = Field(
        10, description="Minimum percentage points between progress updates"
    )

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
        raise HTTPException(status_code=500, detail=str(e))


# === Ingest a single GCS file ===
@app.post("/ingest-file")
async def ingest_single_file(payload: FileIngestRequest, request: Request): # Added request: Request
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
            # Remove gs:// and bucket name to get the actual file path
            parts = file_path[5:].split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid GCS path format: {file_path}")
            bucket_name, actual_path = parts
            if bucket_name != GCS_BUCKET_NAME:
                raise ValueError(f"File is in bucket {bucket_name} but service is configured for {GCS_BUCKET_NAME}")
            file_path = actual_path

        # Step 2: Reading file
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
            # Add additional context for debugging
            logger.error(f"Reader kwargs: {reader_kwargs}")
            logger.error(f"Original file path: {payload.file_path}")
            logger.error(f"Cleaned file path: {file_path}")

            # Update progress to failed state if we have link_id
            if payload.link_id:
                try:
                    await settings.update_file_progress(
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

        # Step 3: Processing documents
        total_docs = len(documents)
        if total_docs == 0:
            raise HTTPException(status_code=400, detail=f"No documents extracted from file: {file_path}")

        logger.info(f"📄 Processing {total_docs} documents from file")
        processed_docs = 0

        # Send initial progress update
        await settings.update_file_progress(
            file_uuid=payload.file_uuid, progress=0, processed_docs=0, total_docs=total_docs, link_id=payload.link_id
        )

        # === Use Embedder from app.state ===
        embedder = None
        current_embed_dim = EMBED_DIM  # Default, will try to update based on model
        logger.info(f"Requested embedding provider: {payload.embedding_provider}, model: {payload.embedding_model}")

        if payload.embedding_provider == "openai":
            embedder = request.app.state.openai_embedder
            if not embedder:
                raise HTTPException(status_code=500, detail="OpenAI embedder not available or not initialized.")
            # Update the model for this specific request if it's different from the default
            # Assuming the embedder in app.state is initialized with a default model or no model
            embedder.model = payload.embedding_model # This might reconfigure if model changes often.
                                                      # If OpenAIEmbedding doesn't allow model change after init,
                                                      # then we might need to store multiple instances or re-init.
                                                      # For now, assume it's configurable.
            if hasattr(embedder, "dimensions") and embedder.dimensions:
                current_embed_dim = embedder.dimensions
            else: # Fallback for older LlamaIndex versions or if dimensions not readily available
                # Try to get dimensions from a known mapping or default
                if payload.embedding_model == "text-embedding-3-small":
                    current_embed_dim = 1536
                elif payload.embedding_model == "text-embedding-3-large":
                    current_embed_dim = 3072
                elif payload.embedding_model == "text-embedding-ada-002":
                     current_embed_dim = 1536
                else:
                    logger.warning(
                        f"Could not determine dimensions for OpenAI model {payload.embedding_model}. Falling back to default EMBED_DIM={EMBED_DIM}."
                    )

        elif payload.embedding_provider == "google":
            gemini_client = request.app.state.gemini_embedder_client
            if not gemini_client:
                raise HTTPException(status_code=500, detail="Google Gemini embedder client not available or not initialized.")
            try:
                # Create a new instance with the specific model for this request
                embedder = GeminiEmbedding(model_name=payload.embedding_model, api_key=os.getenv("GOOGLE_API_KEY"))

                if "embedding-004" in payload.embedding_model:
                    current_embed_dim = 768
                elif "embedding-001" in payload.embedding_model: # Older model, also 768
                    current_embed_dim = 768
                # Add more known models here or find a programmatic way if available
                else:
                     # If model is unknown, try to get from a 'dimensions' attribute if it exists (speculative)
                    if hasattr(embedder, "_model") and hasattr(embedder._model, "output_dimensionality"): # Check internal structure
                        current_embed_dim = embedder._model.output_dimensionality
                    elif hasattr(embedder, "dimensions") and embedder.dimensions: # Check direct attribute
                        current_embed_dim = embedder.dimensions
                    else:
                        logger.warning(
                            f"Cannot determine dimension for Google model {payload.embedding_model}. Using default {EMBED_DIM}. This might be incorrect."
                        )
            except Exception as e:
                logger.error(f"Failed to initialize GeminiEmbedding for request: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to initialize Google Gemini Embedding for request: {str(e)}")
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported embedding provider: {payload.embedding_provider}")

        if embedder is None:
            raise HTTPException(status_code=500, detail="Failed to initialize or retrieve embedder.")

        logger.info(f"Using embedder: {embedder.__class__.__name__} with model {payload.embedding_model}")
        logger.info(f"Using embedding dimension: {current_embed_dim} for vector store.")

        vector_store = PGVectorStore(
            connection_string=POSTGRES_URL,
            async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=payload.vector_table_name,
            embed_dim=current_embed_dim,  # Use determined dimension
            schema_name=SCHEMA_NAME,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # Initialize VectorStoreIndex without documents initially
        # Nodes will be added asynchronously.
        index = VectorStoreIndex(
            nodes=[], # Start with an empty index
            storage_context=storage_context,
            embed_model=embedder
        )

        # Process documents in batches
        batch_size = payload.batch_size # Use batch_size from payload
        text_splitter = TokenTextSplitter(chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap)

        last_reported_progress = 0

        try:
            for i in range(0, total_docs, batch_size):
                batch_documents = documents[i : i + batch_size]
                try:
                    # Split documents into chunks (nodes)
                    # Document objects are a subclass of Node, so they can be used directly.
                    nodes_to_insert = []
                    for doc in batch_documents:
                        # Add file_uuid to metadata of each document/node before splitting
                        # This ensures that all nodes derived from this document have this metadata.
                        # The GCSReader might already put file_path in metadata. Let's ensure file_uuid too.
                        doc_metadata = doc.metadata or {}
                        doc_metadata["file_uuid"] = payload.file_uuid # Ensure file_uuid is in metadata for deletion
                        doc.metadata = doc_metadata

                        text_chunks = text_splitter.split_text(doc.text)
                        for chunk_text in text_chunks:
                            node = Document(text=chunk_text, metadata=doc.metadata)
                            nodes_to_insert.append(node)

                    if not nodes_to_insert:
                        logger.info(f"Batch {i // batch_size + 1} resulted in no nodes after splitting. Skipping.")
                        processed_docs += len(batch_documents) # Count original documents as processed
                        continue

                    logger.info(f"Inserting {len(nodes_to_insert)} nodes from {len(batch_documents)} original documents in batch {i // batch_size + 1}.")
                    # Asynchronously insert nodes into the index.
                    # This in turn uses the vector_store's async_add method.
                    await index.async_insert_nodes(nodes_to_insert)

                    processed_docs += len(batch_documents)

                    # Calculate progress
                    current_progress = (processed_docs / total_docs) * 100

                    # Update progress in database, but only if it has changed significantly
                    if current_progress >= last_reported_progress + payload.progress_update_frequency or processed_docs == total_docs:
                        await settings.update_file_progress(
                            file_uuid=payload.file_uuid,
                            progress=current_progress,
                            processed_docs=processed_docs,
                            total_docs=total_docs,
                            link_id=payload.link_id,
                        )
                        last_reported_progress = current_progress

                except HTTPException: # Re-raise HTTPExceptions directly
                    raise
                except Exception as e:
                    error_message = f"❌ Failed to process batch {i // batch_size + 1}: {str(e)}"
                    logger.error(error_message)
                    # Update progress to failed state
                    if payload.link_id:
                        try:
                            # Report current progress before error
                            current_progress_on_error = (processed_docs / total_docs) * 100
                            await settings.update_file_progress(
                                file_uuid=payload.file_uuid,
                                progress=current_progress_on_error,
                                processed_docs=processed_docs,
                                total_docs=total_docs,
                                link_id=payload.link_id,
                                error=error_message  # Include error message in progress update
                            )
                        except Exception as progress_e:
                            logger.error(f"Failed to update progress after batch error: {progress_e}")
                    raise HTTPException(status_code=500, detail=error_message)

            # Ensure final progress update if not already sent
            if last_reported_progress < 100 and processed_docs == total_docs:
                await settings.update_file_progress(
                    file_uuid=payload.file_uuid,
                    progress=100,
                    processed_docs=total_docs,
                    total_docs=total_docs,
                    link_id=payload.link_id,
                )

            return {
                "status": "completed",
                "message": f"Successfully processed {total_docs} documents, generating {sum(1 for i in range(0, total_docs, batch_size) for doc in documents[i:i+batch_size] for _ in text_splitter.split_text(doc.text))} nodes.",
                "total_original_documents": total_docs,
                "file_path": file_path,
            }
        except HTTPException: # Ensure HTTPExceptions from batch processing are re-raised
            raise
        except Exception as e:
            error_message_processing = f"❌ Error during document processing loop: {str(e)}"
            logger.error(error_message_processing)
            # Ensure we update progress to failed state
            if payload.link_id:
                try:
                    # Use progress from the point of failure if available
                    current_progress_on_error = (processed_docs / total_docs) * 100 if total_docs > 0 else 0
                    await settings.update_file_progress(
                        file_uuid=payload.file_uuid,
                        progress=current_progress_on_error,
                        processed_docs=processed_docs,
                        total_docs=total_docs,
                        link_id=payload.link_id,
                        error=error_message_processing
                    )
                except Exception as progress_e:
                    logger.error(f"Failed to update progress after processing error: {progress_e}")
            raise HTTPException(status_code=500, detail=error_message_processing)

    except HTTPException: # Catch HTTPExceptions from earlier stages (file reading, setup)
        raise
    except Exception as e: # Catch any other general exceptions
        error_message_general = f"❌ Error ingesting file {payload.file_path}: {str(e)}"
        logger.error(error_message_general)
        # Attempt to update progress with error if file_uuid and link_id are available
        if hasattr(payload, 'file_uuid') and hasattr(payload, 'link_id') and payload.link_id is not None:
            try:
                await settings.update_file_progress(
                    file_uuid=payload.file_uuid,
                    progress=0, # Or last known progress if available
                    processed_docs=0, # Or last known count
                    total_docs=0, # Or actual total if known
                    link_id=payload.link_id,
                    error=error_message_general
                )
            except Exception as progress_e:
                logger.error(f"Failed to update progress after general error: {progress_e}")
        raise HTTPException(status_code=500, detail=error_message_general)


# === Delete vectors for a file ===
@app.post("/delete-vectors")
async def delete_vectors(payload: DeleteVectorRequest):
    try:
        logger.info(f"🗑️ Deleting vectors for file: {payload.file_uuid} from table: {payload.vector_table_name}")

        # Initialize vector store
        # Note: embed_dim is technically not needed for deletion but PGVectorStore constructor might require it.
        # Using the default EMBED_DIM here. If tables can have different dims, this might need adjustment,
        # but deletion is usually based on metadata filters, not vector dimensions.
        vector_store = PGVectorStore(
            connection_string=POSTGRES_URL,
            async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=payload.vector_table_name,
            embed_dim=EMBED_DIM, # Default, as actual dim doesn't affect metadata-based deletion
            schema_name=SCHEMA_NAME,
        )

        # Asynchronously delete vectors with matching file_uuid in metadata
        # The `delete` method in PGVectorStore might not be async.
        # Let's check LlamaIndex source or assume it's sync for now.
        # If it's sync, it will block. If an async version (e.g., `async_delete`) exists, prefer that.
        # For now, assuming it's synchronous as typical DB delete operations are often so.
        # If this blocks, it's a point for future optimization.

        # LlamaIndex PGVectorStore's delete method is synchronous.
        # To make this non-blocking, one would typically run it in a thread pool.
        # from fastapi import BackgroundTasks
        # async def delete_in_background(vector_store, file_uuid):
        #     vector_store.delete(filter_dict={"file_uuid": file_uuid})
        # background_tasks.add_task(delete_in_background, vector_store, payload.file_uuid)
        # However, for simplicity and given it's a delete operation, we'll call it directly.
        # This might block if many vectors match.

        logger.info(f"Attempting to delete vectors with metadata filter: {{'file_uuid': '{payload.file_uuid}'}}")

        # Check if the vector store has an async delete method.
        # Based on common patterns, if `async_add` exists, `async_delete` might too.
        # A quick check of LlamaIndex source for PGVectorStore would confirm.
        # As of recent versions, PGVectorStore has `delete` (sync) and `async_delete`.

        # Let's assume `async_delete` is available and use it.
        if hasattr(vector_store, 'async_delete'):
            await vector_store.async_delete(filter_dict={"file_uuid": payload.file_uuid})
            # The `delete` method returns `None`, so we can't get a count directly from it.
            # We'd have to query before and after if a count is strictly needed, or rely on logs.
            logger.info(f"✅ Async delete call completed for file_uuid: {payload.file_uuid}.")
            # Since async_delete doesn't return a count, we set it to -1 or a similar indicator.
            deleted_count = -1 # Indicates successful call, but count not returned by this method.
        else:
            # Fallback to synchronous delete if async_delete is not available
            logger.warning("async_delete not found on PGVectorStore, falling back to synchronous delete. This may block.")
            vector_store.delete(filter_dict={"file_uuid": payload.file_uuid}) # This is synchronous
            # Similarly, the synchronous delete also returns None.
            deleted_count = -1 # Indicates successful call, but count not returned.

        return {
            "status": "success",
            "message": f"Delete operation completed for file_uuid: {payload.file_uuid}. Count of deleted vectors not directly returned by method.",
            "deleted_count_info": "Count not returned by delete method (-1 indicates call success)",
            "file_uuid": payload.file_uuid,
            "vector_table": payload.vector_table_name,
        }

    except Exception as e:
        logger.error(f"❌ Error deleting vectors for file_uuid {payload.file_uuid}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# === Healthcheck route (for Cloud Run probe) ===
@app.get("/")
async def root():
    return {"message": "LlamaIndex GCS ingestion service is alive!"}


# === Run server locally (for dev) ===
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
