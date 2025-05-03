from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import traceback

from llama_index.readers.gcs import GCSReader
from llama_index.readers.google import GoogleDriveReader
from llama_index.core import VectorStoreIndex, StorageContext
from sqlalchemy import create_engine, text
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.gemini import GeminiEmbedding

# === Load ENV ===
load_dotenv()
POSTGRES_URL = os.getenv("POSTGRES_URL")
GCS_BUCKET = os.getenv("GCS_BUCKET")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

# === Log ENV ===
print("🔧 ENV Loaded:")
print(f"POSTGRES_URL={POSTGRES_URL}")
print(f"GCS_BUCKET={GCS_BUCKET}")
print(f"GOOGLE_CREDENTIALS_PATH={GOOGLE_CREDENTIALS_PATH}")

# === FastAPI App ===
app = FastAPI()

# === Request Models ===
class IngestRequest(BaseModel):
    gcs_path: str
    knowledgebase_id: str

class DriveIngestRequest(BaseModel):
    folder_id: str
    knowledgebase_id: str

# === Embedder Selector ===
def get_embedder(embed_model_id: str):
    print(f"🔍 Getting embedder for: {embed_model_id}")
    if embed_model_id == "text-embedding-ada-002":
        return OpenAIEmbedding(model=embed_model_id)
    elif embed_model_id.startswith("gemini/"):
        return GeminiEmbedding(model=embed_model_id)
    raise ValueError(f"❌ Unsupported embed model: {embed_model_id}")

# === Vector Store Loader ===
def get_kb_and_vector_store(kb_id: str):
    print(f"🔎 Fetching KnowledgeBase config for: {kb_id}")
    engine = create_engine(POSTGRES_URL)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT vector_table_name, embed_model_id FROM knowledge_base WHERE knowledgebase_id = :kb"),
            {"kb": kb_id}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="KnowledgeBase not found")
        table_name, embed_model_id = result

    embed_model = get_embedder(embed_model_id)
    vector_store = PGVectorStore(
        engine=engine,
        table_name=table_name,
        embed_dim=embed_model.dimensions
    )
    return embed_model, vector_store

# === Ingest Single File from GCS ===
@app.post("/ingest")
async def ingest_file(payload: IngestRequest):
    print(f"📥 /ingest for file: {payload.gcs_path}")
    try:
        if not any(payload.gcs_path.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
            return {"status": "skipped", "reason": "unsupported file type"}

        reader = GCSReader(
            bucket=GCS_BUCKET,
            key=payload.gcs_path,
            service_account_key_path=GOOGLE_CREDENTIALS_PATH
        )
        documents = reader.load_data()
        print(f"📄 Loaded {len(documents)} documents")

        embed_model, vector_store = get_kb_and_vector_store(payload.knowledgebase_id)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)

        return {"status": "success", "file": payload.gcs_path, "documents": len(documents)}

    except Exception as e:
        print("❌ Error in /ingest")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Ingest All Files from GCS Prefix ===
@app.post("/ingest-all")
async def ingest_all(payload: IngestRequest):
    print(f"📥 /ingest-all for prefix: {payload.gcs_path}")
    try:
        reader = GCSReader(
            bucket=GCS_BUCKET,
            prefix=payload.gcs_path,
            service_account_key_path=GOOGLE_CREDENTIALS_PATH
        )
        documents = reader.load_data()
        print(f"📁 Total files found: {len(documents)}")

        documents = [
            doc for doc in documents
            if any(doc.metadata.get("file_path", "").endswith(ext) for ext in SUPPORTED_EXTENSIONS)
        ]
        print(f"✅ Filtered to {len(documents)} supported files")

        embed_model, vector_store = get_kb_and_vector_store(payload.knowledgebase_id)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)

        return {
            "status": "success",
            "gcs_path": payload.gcs_path,
            "knowledgebase_id": payload.knowledgebase_id,
            "vector_table": vector_store.table_name,
            "total_documents": len(documents),
            "embedded_model": embed_model.__class__.__name__,
        }

    except Exception as e:
        print("❌ Error in /ingest-all")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Ingest from Google Drive Folder ===
@app.post("/ingest-drive")
async def ingest_drive(payload: DriveIngestRequest):
    print(f"📥 /ingest-drive for folder: {payload.folder_id}")
    try:
        reader = GoogleDriveReader()
        documents = reader.load_data(folder_id=payload.folder_id)
        print(f"📄 Loaded {len(documents)} from Drive")

        embed_model, vector_store = get_kb_and_vector_store(payload.knowledgebase_id)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)

        return {"status": "success", "folder_id": payload.folder_id, "documents": len(documents)}

    except Exception as e:
        print("❌ Error in /ingest-drive")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === List GCS Resources ===
@app.get("/test-list-gcs")
async def test_list_gcs(prefix: str = ""):
    print(f"🔍 Listing GCS resources under prefix: {prefix}")
    try:
        reader = GCSReader(
            bucket=GCS_BUCKET,
            prefix=prefix,
            service_account_key_path=GOOGLE_CREDENTIALS_PATH
        )
        print('documents next')
        documents = reader.load_data()
        resources = reader.list_resources()

        file_list = [doc.metadata.get("file_path", "[no path]") for doc in documents]
        print(file_list)
        return {
            "bucket": GCS_BUCKET,
            "prefix": prefix,
            "total_documents": len(documents),
            "total_resources": len(resources),
            "files": file_list
        }

    except Exception as e:
        print("❌ Error in /test-list-gcs")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
