import json
import logging
from tqdm import tqdm
from sqlalchemy import create_engine
from llama_index.readers.gcs import GCSReader
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.embeddings.openai import OpenAIEmbedding
from dotenv import load_dotenv
import os
# === Configuration ===
CREDENTIALS_PATH = ".gcp/creds/storage.json"
GCS_BUCKET = "bh-reggie-media"
PREFIX = "reggie-data/global/library/"
POSTGRES_URL = "postgresql://ai:ai@localhost:5532/ai"
VECTOR_TABLE_NAME = "pdf_documents"
EMBEDDING_MODEL = "text-embedding-ada-002"
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

# === Logging Setup ===
logging.basicConfig(level=logging.INFO)
logging.getLogger("llama_index.readers.gcs").setLevel(logging.INFO)

# === Load GCP Credentials ===
with open(CREDENTIALS_PATH, "r") as f:
    service_account_key_json = json.load(f)

# === Initialize GCS Reader ===
reader = GCSReader(
    bucket=GCS_BUCKET,
    prefix=PREFIX,
    service_account_key_path=CREDENTIALS_PATH
)

# === Load GCS Resources ===
print(f"📁 Listing resources in: {GCS_BUCKET}/{PREFIX}")
resources = reader.list_resources()
#Testing 1 file only
resources = resources[:1]
print(f"🔎 Found {len(resources)} resources")

# === Load all documents ===
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

# === Initialize Embedder and Vector Store ===
embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=openai_api_key)
# vector_store = PGVectorStore(
#     connection_string="postgresql://ai:ai@localhost:5532/ai",
#     table_name="pdf_documents",
#     embed_dim=1536,
#     schema_name="public"
# )
from llama_index.vector_stores.postgres import PGVectorStore

vector_store = PGVectorStore(
    connection_string=POSTGRES_URL,
    async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
    table_name="pdf_documents",
    embed_dim=1536,  # or embedder.dimensions
    schema_name="ai"
)



# === Create Index and Persist ===
storage_context = StorageContext.from_defaults(vector_store=vector_store)
VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embedder)

{
    "total_resources": len(resources),
    "total_documents_indexed": len(documents),
    "vector_table": VECTOR_TABLE_NAME
}
