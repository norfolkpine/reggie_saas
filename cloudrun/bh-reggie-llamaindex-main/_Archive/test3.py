import os
import json
import logging
from tqdm import tqdm
from dotenv import load_dotenv
from llama_index.readers.gcs import GCSReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import VectorStoreIndex, StorageContext

# === Load environment variables ===
load_dotenv()
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GCS_BUCKET = os.getenv("GCS_BUCKET")
PREFIX = os.getenv("GCS_PREFIX")
POSTGRES_URL = os.getenv("POSTGRES_URL")
VECTOR_TABLE_NAME = os.getenv("PGVECTOR_TABLE")
SCHEMA_NAME = os.getenv("PGVECTOR_SCHEMA")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-ada-002"

# === Logging Setup ===
logging.basicConfig(level=logging.INFO)
logging.getLogger("llama_index.readers.gcs").setLevel(logging.INFO)

# === Initialize GCS Reader ===
reader = GCSReader(
    bucket=GCS_BUCKET,
    prefix=PREFIX,
    service_account_key_path=CREDENTIALS_PATH
)

# === List and limit resources ===
print(f"📁 Listing resources in: {GCS_BUCKET}/{PREFIX}")
resources = reader.list_resources()
resources = resources[:1]  # Test one file
print(f"🔎 Found {len(resources)} resources")

# === Load documents from GCS ===
documents = []
for name in tqdm(resources, desc="📦 Loading and parsing documents"):
    try:
        result = reader.load_resource(name)
        if isinstance(result, list):
            for doc in result:
                documents.append(doc)
                print(f"✅ Loaded (multi): {name} | Characters: {len(doc.text)}")
        else:
            documents.append(result)
            print(f"✅ Loaded: {name} | Characters: {len(result.text)}")
    except Exception as e:
        print(f"❌ Failed to load {name}: {str(e)}")

# === Initialize embedder and vector store ===
embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
vector_store = PGVectorStore(
    connection_string=POSTGRES_URL,
    async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
    table_name=VECTOR_TABLE_NAME,
    embed_dim=1536,#embed_dim=embedder.dimensions,
    schema_name=SCHEMA_NAME
)

# === Index and persist embeddings ===
storage_context = StorageContext.from_defaults(vector_store=vector_store)
VectorStoreIndex.from_documents(
    documents,
    storage_context=storage_context,
    embed_model=embedder
)

# === Summary ===
{
    "total_resources": len(resources),
    "total_documents_indexed": len(documents),
    "vector_table": VECTOR_TABLE_NAME
}
