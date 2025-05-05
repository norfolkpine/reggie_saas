import logging
import os
from contextlib import asynccontextmanager
from typing import Optional
import asyncio
import traceback

import httpx
from fastapi import FastAPI, HTTPException
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.gcs import GCSReader
from llama_index.vector_stores.postgres import PGVectorStore
from pydantic import BaseModel, Field
from tqdm import tqdm
import urllib.parse


def load_env(secret_id=None, env_file=".env"):
    """Load environment variables from Secret Manager or local .env file."""
    try:
        if secret_id:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            project_id = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "bh-crypto"))
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            env_content = response.payload.data.decode("utf-8")
            for line in env_content.splitlines():
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value
            print(f"✅ Loaded environment from Secret Manager: {secret_id}")
            return
    except Exception as e:
        print(f"⚠️ Failed to load secret '{secret_id}', falling back to local env: {e}")

    from dotenv import load_dotenv

    if load_dotenv(env_file):
        print(f"✅ Loaded environment from {env_file}")
    else:
        print(f"⚠️ Failed to load {env_file}")


# Load env (Secret Manager first, fallback to .env)
load_env(secret_id="llamaindex-ingester-env")

# === Config Variables ===
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

# Validate required environment variables
if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")

POSTGRES_URL = os.getenv("POSTGRES_URL")
VECTOR_TABLE_NAME = os.getenv("PGVECTOR_TABLE")
SCHEMA_NAME = os.getenv("PGVECTOR_SCHEMA", "public")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))
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
        masked_key = f"{self.DJANGO_API_KEY[:4]}...{self.DJANGO_API_KEY[-4:]}" if self.DJANGO_API_KEY else "None"
        logger.info(f"🔑 Using System API Key: {masked_key}")

        return {
            "Authorization": f"Api-Key {self.DJANGO_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-Source": "cloud-run-ingestion",
        }

    async def update_file_progress(
        self, file_uuid: str, progress: float, processed_docs: int, total_docs: int, link_id: Optional[int] = None, error: Optional[str] = None
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
    # Load environment variables
    load_env(secret_id="llamaindex-ingester-env")

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
                        logger.info("✅ Django API key validated successfully (Celery is down but authentication worked)")
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
    file_limit: Optional[int] = None
    vector_table_name: str


class FileIngestRequest(BaseModel):
    file_path: str = Field(..., description="Full GCS path to the file")
    vector_table_name: str = Field(..., description="Name of the vector table to store embeddings")
    file_uuid: str = Field(..., description="UUID of the file in Django")
    link_id: Optional[int] = Field(None, description="Optional link ID for tracking specific ingestion")
    embedding_model: Optional[str] = Field(EMBEDDING_MODEL, description="Model to use for embeddings")
    chunk_size: Optional[int] = Field(1000, description="Size of text chunks")
    chunk_overlap: Optional[int] = Field(200, description="Overlap between chunks")
    batch_size: Optional[int] = Field(20, description="Number of documents to process in each batch")
    progress_update_frequency: Optional[int] = Field(10, description="Minimum percentage points between progress updates")

    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "gs://your-bucket/path/to/file.pdf",
                "vector_table_name": "your_vector_table",
                "file_uuid": "123e4567-e89b-12d3-a456-426614174000",
                "link_id": 1,
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
def index_documents(docs, source: str, vector_table_name: str):
    if not docs:
        raise HTTPException(status_code=404, detail=f"No documents found for {source}")

    logger.info(f"📊 Starting embedding for {len(docs)} documents from source: {source}")
    embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)

    vector_store = PGVectorStore(
        connection_string=POSTGRES_URL,
        async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
        table_name=vector_table_name,
        embed_dim=EMBED_DIM,
        schema_name=SCHEMA_NAME,
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info("🧠 Building VectorStoreIndex...")
    VectorStoreIndex.from_documents(docs, storage_context=storage_context, embed_model=embedder)
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

        return index_documents(documents, source=payload.gcs_prefix, vector_table_name=payload.vector_table_name)

    except Exception as e:
        logger.error("❌ Ingestion error", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === Ingest a single GCS file ===
@app.post("/ingest-file")
async def ingest_single_file(payload: FileIngestRequest):
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
                if 'decoded_path' in locals():
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
                        error=error_msg
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

        embedder = OpenAIEmbedding(model=payload.embedding_model, api_key=OPENAI_API_KEY)
        vector_store = PGVectorStore(
            connection_string=POSTGRES_URL,
            async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=payload.vector_table_name,
            embed_dim=EMBED_DIM,
            schema_name=SCHEMA_NAME,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # Process documents in batches
        batch_size = 5
        text_splitter = TokenTextSplitter(chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap)

        try:
            for i in range(0, total_docs, batch_size):
                batch = documents[i : i + batch_size]
                try:
                    # Split documents into chunks
                    chunked_docs = []
                    for doc in batch:
                        text_chunks = text_splitter.split_text(doc.text)
                        chunked_docs.extend([Document(text=chunk, metadata=doc.metadata) for chunk in text_chunks])

                    # Index the chunked documents
                    VectorStoreIndex.from_documents(chunked_docs, storage_context=storage_context, embed_model=embedder)
                    processed_docs += len(batch)

                    # Calculate progress
                    progress = (processed_docs / total_docs) * 100

                    # Update progress in database
                    await settings.update_file_progress(
                        file_uuid=payload.file_uuid,
                        progress=progress,
                        processed_docs=processed_docs,
                        total_docs=total_docs,
                        link_id=payload.link_id,
                    )

                except Exception as e:
                    logger.error(f"❌ Failed to process batch {i // batch_size + 1}: {str(e)}")
                    # Update progress to failed state
                    if payload.link_id:
                        try:
                            await settings.update_file_progress(
                                file_uuid=payload.file_uuid,
                                progress=progress,  # Keep the last progress
                                processed_docs=processed_docs,
                                total_docs=total_docs,
                                link_id=payload.link_id,
                            )
                        except Exception as progress_e:
                            logger.error(f"Failed to update progress after batch error: {progress_e}")
                    raise HTTPException(status_code=500, detail=f"Failed to process documents: {str(e)}")

            # Send final progress update
            await settings.update_file_progress(
                file_uuid=payload.file_uuid,
                progress=100,
                processed_docs=total_docs,
                total_docs=total_docs,
                link_id=payload.link_id,
            )

            return {
                "status": "completed",
                "message": f"Successfully processed {total_docs} documents",
                "total_docs": total_docs,
                "file_path": file_path,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error during document processing: {str(e)}")
            # Ensure we update progress to failed state
            if payload.link_id:
                try:
                    await settings.update_file_progress(
                        file_uuid=payload.file_uuid,
                        progress=progress if "progress" in locals() else 0,
                        processed_docs=processed_docs,
                        total_docs=total_docs,
                        link_id=payload.link_id,
                    )
                except Exception as progress_e:
                    logger.error(f"Failed to update progress after processing error: {progress_e}")
            raise HTTPException(status_code=500, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error ingesting file {payload.file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
        deleted_count = vector_store.delete(
            filter_dict={"file_uuid": payload.file_uuid}
        )

        logger.info(f"✅ Successfully deleted {deleted_count} vectors")
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "file_uuid": payload.file_uuid,
            "vector_table": payload.vector_table_name
        }

    except Exception as e:
        logger.error(f"❌ Error deleting vectors: {str(e)}")
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
