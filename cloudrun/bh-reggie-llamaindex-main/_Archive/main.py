from fastapi import FastAPI, Request
from pydantic import BaseModel
from llama_index.readers.gcs import GCSReader
from llama_index.readers.google import GoogleDriveReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import VectorStoreIndex, StorageContext
from sqlalchemy import create_engine
import os

app = FastAPI()

# ENV VARS
GCS_BUCKET = os.getenv("GCS_BUCKET")
POSTGRES_URL = os.getenv("POSTGRES_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_DIM = 1536

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

class IngestRequest(BaseModel):
    gcs_path: str
    vector_table: str

class DriveIngestRequest(BaseModel):
    folder_id: str
    vector_table: str

@app.post("/ingest")
async def ingest_file(payload: IngestRequest):
    if not any(payload.gcs_path.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        return {"status": "skipped", "reason": "unsupported file type"}

    reader = GCSReader(bucket=GCS_BUCKET, prefix=payload.gcs_path)
    documents = reader.load_data()

    embed_model = OpenAIEmbedding(model="text-embedding-ada-002", api_key=OPENAI_API_KEY)
    engine = create_engine(POSTGRES_URL)
    vector_store = PGVectorStore(engine=engine, table_name=payload.vector_table, embed_dim=EMBED_DIM)

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)

    return {"status": "success", "file": payload.gcs_path, "documents": len(documents)}


@app.post("/ingest-all")
async def ingest_all(payload: IngestRequest):
    reader = GCSReader(bucket=GCS_BUCKET, prefix=payload.gcs_path)
    documents = reader.load_data()
    documents = [
        doc for doc in documents
        if any(doc.metadata.get("file_path", "").endswith(ext) for ext in SUPPORTED_EXTENSIONS)
    ]

    embed_model = OpenAIEmbedding(model="text-embedding-ada-002", api_key=OPENAI_API_KEY)
    engine = create_engine(POSTGRES_URL)
    vector_store = PGVectorStore(engine=engine, table_name=payload.vector_table, embed_dim=EMBED_DIM)

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)

    return {"status": "success", "files": len(documents)}


@app.post("/ingest-drive")
async def ingest_drive(payload: DriveIngestRequest):
    reader = GoogleDriveReader()
    documents = reader.load_data(folder_id=payload.folder_id)

    embed_model = OpenAIEmbedding(model="text-embedding-ada-002", api_key=OPENAI_API_KEY)
    engine = create_engine(POSTGRES_URL)
    vector_store = PGVectorStore(engine=engine, table_name=payload.vector_table, embed_dim=EMBED_DIM)

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)

    return {"status": "success", "folder_id": payload.folder_id, "documents": len(documents)}
