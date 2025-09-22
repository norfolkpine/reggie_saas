# Functions in main.py

## Core Functions

### Environment & Configuration
- `load_env(secret_id="llamaindex-ingester-env", env_file=".env")` - Load environment variables from Secret Manager or .env file

### Vector Store Management
- `get_vector_store(vector_table_name, current_embed_dim)` - Get cached vector store instance

### Document Processing
- `index_documents(docs, source: str, vector_table_name: str, embed_model)` - Common indexing logic for documents
- `process_single_file(payload: FileIngestRequest)` - Process a single file for ingestion

### FastAPI Endpoints
- `lifespan(app: FastAPI)` - Startup and shutdown events for FastAPI app
- `ingest_gcs_docs(payload: IngestRequest)` - Ingest documents by GCS prefix (bulk mode)
- `ingest_single_file(payload: FileIngestRequest)` - Queue single file ingestion
- `delete_vectors(payload: DeleteVectorRequest)` - Delete vectors for a file
- `root()` - Healthcheck route

## Classes

### Pydantic Models
- `Settings` - Settings object for progress updates with Django API
- `IngestRequest` - Request model for GCS bulk ingestion
- `FileIngestRequest` - Request model for single file ingestion
- `DeleteVectorRequest` - Request model for vector deletion

## Method Details

### Settings Class Methods
- `auth_headers` (property) - Return properly formatted auth headers for system API key
- `update_file_progress_sync(file_uuid, progress, processed_docs, total_docs, link_id=None, error=None)` - Update file ingestion progress
- `validate_auth_response(response)` - Validate authentication response and log helpful messages

### FileIngestRequest Class Methods
- `clean_file_path()` - Clean and validate the file path

## Summary
- **Total Functions**: 8 functions + 4 classes
- **FastAPI Endpoints**: 5 endpoints
- **Core Features**: File ingestion, vector storage, progress tracking, GCS integration
