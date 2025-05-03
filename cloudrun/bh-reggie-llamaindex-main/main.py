from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
import os
import logging
from typing import Optional
from tqdm import tqdm
from llama_index.readers.gcs import GCSReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import VectorStoreIndex, StorageContext, Document
import httpx

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

# === Logging Setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("llama_index")
logger.setLevel(logging.INFO)

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
    file_path: str
    vector_table_name: str
    file_id: int  # Add file ID to track progress

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
        
        # Step 1: Reading file
        reader_kwargs = {
            "bucket": GCS_BUCKET,
            "key": payload.file_path
        }
        reader = GCSReader(**reader_kwargs)
        result = reader.load_data()
        documents = result if isinstance(result, list) else [result]
        
        # Step 2: Processing documents
        total_docs = len(documents)
        processed_docs = 0
        
        embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
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
        for i in range(0, total_docs, batch_size):
            batch = documents[i:i + batch_size]
            VectorStoreIndex.from_documents(batch, storage_context=storage_context, embed_model=embedder)
            processed_docs += len(batch)
            
            # Calculate progress
            progress = (processed_docs / total_docs) * 100
            
            # Update progress in database
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{settings.DJANGO_API_URL}/api/v1/files/{payload.file_id}/update-progress/",
                        json={
                            "progress": progress,
                            "processed_docs": processed_docs,
                            "total_docs": total_docs
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to update progress: {e}")
        
        return {
            "status": "completed",
            "message": f"Successfully processed {total_docs} documents",
            "total_docs": total_docs
        }
        
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
