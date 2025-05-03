from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import json
import logging
from tqdm import tqdm
from llama_index.readers.gcs import GCSReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import VectorStoreIndex, StorageContext, Document

# === Load environment variables ===
load_dotenv()
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
app = FastAPI()

# === Request Models ===
class IngestRequest(BaseModel):
    gcs_prefix: str
    file_limit: int = 1

class FileIngestRequest(BaseModel):
    file_path: str  # exact GCS key like "reggie-data/global/library/C2025C00029VOL01.pdf"

# === Common indexing logic ===
def index_documents(docs, source: str):
    if not docs:
        raise HTTPException(status_code=404, detail=f"No documents found for {source}")

    logger.info(f"📊 Starting embedding for {len(docs)} documents from source: {source}")
    embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)

    vector_store = PGVectorStore(
        connection_string=POSTGRES_URL,
        async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
        table_name=VECTOR_TABLE_NAME,
        embed_dim=EMBED_DIM,
        schema_name=SCHEMA_NAME
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info("🧠 Building VectorStoreIndex...")
    index = VectorStoreIndex.from_documents(docs, storage_context=storage_context, embed_model=embedder)
    logger.info("✅ Embedding and indexing complete.")

    return {
        "indexed_documents": len(docs),
        "source": source,
        "vector_table": VECTOR_TABLE_NAME
    }

# === Ingest by prefix (bulk mode) ===
@app.post("/ingest-gcs")
async def ingest_gcs_docs(payload: IngestRequest):
    try:
        logger.info(f"🔎 Starting GCS ingestion for prefix: {payload.gcs_prefix}")
        reader = GCSReader(
            bucket=GCS_BUCKET,
            prefix=payload.gcs_prefix,
            service_account_key_path=CREDENTIALS_PATH
        )

        resources = reader.list_resources()[:payload.file_limit]
        logger.info(f"📦 Found {len(resources)} resources")

        documents = []
        for name in tqdm(resources, desc="📂 Loading docs"):
            logger.info(f"📄 Loading file: {name}")
            try:
                result = reader.load_resource(name)
                loaded_docs = result if isinstance(result, list) else [result]
                for doc in loaded_docs:
                    logger.info(f"✅ Loaded document: {name} | Size: {len(doc.text)} characters")
                documents.extend(loaded_docs)
            except Exception as e:
                logger.warning(f"❌ Failed to load {name}: {str(e)}")

        return index_documents(documents, source=payload.gcs_prefix)

    except Exception as e:
        logger.error("❌ Ingestion error", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# === Ingest a single GCS file ===
@app.post("/ingest-file")
async def ingest_single_file(payload: FileIngestRequest):
    try:
        logger.info(f"📄 Ingesting single file: {payload.file_path}")
        reader = GCSReader(
            bucket=GCS_BUCKET,
            key=payload.file_path,
            service_account_key_path=CREDENTIALS_PATH
        )

        result = reader.load_data()
        documents = result if isinstance(result, list) else [result]

        for doc in documents:
            logger.info(f"✅ Parsed document: {payload.file_path} | Size: {len(doc.text)} characters")

        return index_documents(documents, source=payload.file_path)

    except Exception as e:
        logger.error("❌ Single-file ingestion error", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
