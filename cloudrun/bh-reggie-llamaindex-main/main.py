from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
import os
import logging
from typing import Optional
from tqdm import tqdm
from llama_index.readers.gcs import GCSReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import VectorStoreIndex, StorageContext, Document
from llama_index.core.node_parser import TokenTextSplitter
import httpx
import uuid

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
GCS_BUCKET = os.getenv("GCS_BUCKET")
POSTGRES_URL = os.getenv("POSTGRES_URL")
VECTOR_TABLE_NAME = os.getenv("PGVECTOR_TABLE")
SCHEMA_NAME = os.getenv("PGVECTOR_SCHEMA")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-ada-002"
EMBED_DIM = 1536
DJANGO_API_URL = os.getenv("DJANGO_API_URL", "http://localhost:8000")  # Add Django API URL

# === Logging Setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("llama_index")
logger.setLevel(logging.INFO)

# Create settings object for progress updates
class Settings:
    DJANGO_API_URL = DJANGO_API_URL

settings = Settings()

# === FastAPI App ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_env(secret_id="llamaindex-ingester-env")
    yield

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

    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "gs://your-bucket/path/to/file.pdf",
                "vector_table_name": "your_vector_table",
                "file_uuid": "123e4567-e89b-12d3-a456-426614174000",
                "link_id": 1,
                "embedding_model": "text-embedding-ada-002",
                "chunk_size": 1000,
                "chunk_overlap": 200
            }
        }

    def clean_file_path(self) -> str:
        """Clean and validate the file path."""
        path = self.file_path
        if path.startswith('gs://'):
            # Remove bucket name if present
            path = path.split('/', 3)[-1]
        return '/'.join(part for part in path.split('/') if part and part != GCS_BUCKET)

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
        schema_name=SCHEMA_NAME
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info("🧠 Building VectorStoreIndex...")
    VectorStoreIndex.from_documents(docs, storage_context=storage_context, embed_model=embedder)
    logger.info("✅ Embedding and indexing complete.")

    return {
        "indexed_documents": len(docs),
        "source": source,
        "vector_table": vector_table_name
    }

# === Ingest by GCS prefix (bulk mode) ===
@app.post("/ingest-gcs")
async def ingest_gcs_docs(payload: IngestRequest):
    try:
        logger.info(f"🔎 Starting GCS ingestion for prefix: {payload.gcs_prefix}")
        reader_kwargs = {
            "bucket": GCS_BUCKET,
            "prefix": payload.gcs_prefix
        }

        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH

        reader = GCSReader(**reader_kwargs)


        resources = reader.list_resources()
        if payload.file_limit:
            resources = resources[:payload.file_limit]
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
        
        logger.info(f"🔍 Using cleaned file path: {file_path}")
        
        # Step 2: Reading file
        reader_kwargs = {
            "bucket": GCS_BUCKET,
            "key": file_path  # Use cleaned path
        }
        
        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH
            
        logger.info(f"📚 Initializing GCS reader with bucket: {GCS_BUCKET}, key: {file_path}")
        reader = GCSReader(**reader_kwargs)
        
        try:
            result = reader.load_data()
            if not result:
                raise ValueError(f"No content loaded from file: {file_path}")
        except Exception as e:
            logger.error(f"❌ Failed to read file {file_path} from bucket {GCS_BUCKET}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read file: {str(e)}"
            )
            
        documents = result if isinstance(result, list) else [result]
        
        # Step 3: Processing documents
        total_docs = len(documents)
        if total_docs == 0:
            raise HTTPException(
                status_code=400,
                detail=f"No documents extracted from file: {file_path}"
            )
            
        logger.info(f"📄 Processing {total_docs} documents from file")
        processed_docs = 0
        
        embedder = OpenAIEmbedding(model=payload.embedding_model, api_key=OPENAI_API_KEY)
        vector_store = PGVectorStore(
            connection_string=POSTGRES_URL,
            async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=payload.vector_table_name,
            embed_dim=EMBED_DIM,
            schema_name=SCHEMA_NAME
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # Process documents in batches
        batch_size = 5
        text_splitter = TokenTextSplitter(
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap
        )
        
        for i in range(0, total_docs, batch_size):
            batch = documents[i:i + batch_size]
            try:
                # Split documents into chunks
                chunked_docs = []
                for doc in batch:
                    text_chunks = text_splitter.split_text(doc.text)
                    chunked_docs.extend([
                        Document(text=chunk, metadata=doc.metadata)
                        for chunk in text_chunks
                    ])
                
                # Index the chunked documents
                VectorStoreIndex.from_documents(
                    chunked_docs,
                    storage_context=storage_context,
                    embed_model=embedder
                )
                processed_docs += len(batch)
                
                # Calculate progress
                progress = (processed_docs / total_docs) * 100
                logger.info(f"📊 Progress: {progress:.1f}% ({processed_docs}/{total_docs} documents)")
                
                # Update progress in database if file_uuid is provided
                if hasattr(payload, 'file_uuid'):
                    try:
                        progress_url = f"{settings.DJANGO_API_URL}/api/v1/files/{payload.file_uuid}/update-progress/"
                        progress_data = {
                            "progress": progress,
                            "processed_docs": processed_docs,
                            "total_docs": total_docs,
                            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                            "page_count": len(documents),  # For PDFs this will be accurate
                            "embedding_model": payload.embedding_model,
                            "chunk_size": payload.chunk_size,
                            "chunk_overlap": payload.chunk_overlap,
                            "link_id": payload.link_id
                        }
                        logger.info(f"📤 Sending progress update to {progress_url} with data: {progress_data}")
                        
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                progress_url,
                                json=progress_data,
                                timeout=30.0  # 30 second timeout
                            )
                            response.raise_for_status()
                            logger.info(f"✅ Progress update successful: {response.status_code}")
                            
                    except httpx.HTTPError as e:
                        logger.error(f"❌ HTTP error updating progress: {str(e)}")
                        if hasattr(e, 'response'):
                            logger.error(f"Response status: {e.response.status_code}")
                            logger.error(f"Response body: {e.response.text}")
                    except Exception as e:
                        logger.error(f"❌ Failed to update progress: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Failed to process batch {i//batch_size + 1}: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to process documents: {str(e)}"
                )
        
        return {
            "status": "completed",
            "message": f"Successfully processed {total_docs} documents",
            "total_docs": total_docs,
            "file_path": file_path
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error ingesting file {payload.file_path}: {str(e)}")
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
