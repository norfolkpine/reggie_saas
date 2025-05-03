import json
import logging
from tqdm import tqdm
from llama_index.readers.gcs import GCSReader

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("llama_index.readers.gcs").setLevel(logging.INFO)

# Configuration
CREDENTIALS_PATH = ".gcp/creds/storage.json"
GCS_BUCKET = "bh-reggie-media"
PREFIX = "reggie-data/global/library/"

# Load service account credentials
with open(CREDENTIALS_PATH, "r") as f:
    service_account_key_json = json.load(f)

# Initialize the GCS reader
reader = GCSReader(
    bucket=GCS_BUCKET,
    prefix=PREFIX,
    service_account_key_path=CREDENTIALS_PATH
)

# List GCS resources under the prefix
print(f"📁 Listing files in: {GCS_BUCKET}/{PREFIX}")
resources = reader.list_resources()
print(f"🔎 Found {len(resources)} resources")

# Load documents with progress
documents = []
for name in tqdm(resources, desc="📦 Loading files from GCS"):
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

# Summary
{
    "total_resources_found": len(resources),
    "total_documents_loaded": len(documents),
    "sample_document_text": documents[0].text[:200] if documents else "No documents loaded"
}
