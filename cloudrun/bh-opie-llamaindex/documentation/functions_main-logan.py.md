# Functions in main-logan.py

## Core Functions

### Environment & Configuration
- `load_env(secret_id="llamaindex-ingester-env", env_file=".env")` - Load environment variables from Secret Manager or .env file

### Vector Store Management
- `get_vector_store(vector_table_name, current_embed_dim)` - Get cached vector store instance
- `ensure_vault_vector_table_exists()` - Ensure unified Vault vector table exists with LlamaIndex-compatible schema

### File Processing & Text Extraction
- `download_gcs_file(file_path: str) -> bytes` - Download file from Google Cloud Storage
- `download_file_from_gcs(bucket_name: str, file_path: str) -> bytes` - Download file from GCS (alternative implementation)

### Text Extraction Functions (LangExtract/Unstructured)
- `extract_text_from_pdf_langextract(file_content: bytes) -> tuple[str, dict]` - Enhanced PDF extraction using LangExtract
- `extract_text_from_docx_langextract(file_content: bytes) -> tuple[str, dict]` - Enhanced DOCX extraction using LangExtract
- `extract_text_from_pptx_langextract(file_content: bytes) -> tuple[str, dict]` - Enhanced PPTX extraction using LangExtract
- `extract_text_from_excel_langextract(file_content: bytes) -> tuple[str, dict]` - Enhanced Excel extraction using LangExtract

### Text Extraction Fallback Functions
- `extract_text_from_pdf_fallback(file_content: bytes) -> str` - Fallback PDF extraction using PyPDF2
- `extract_text_from_docx_fallback(file_content: bytes) -> str` - Fallback DOCX extraction using python-docx
- `extract_text_from_pptx_fallback(file_content: bytes) -> str` - Fallback PPTX extraction using python-pptx
- `extract_text_from_excel_fallback(file_content: bytes) -> str` - Fallback Excel extraction using openpyxl

### Text Extraction (Basic)
- `extract_text_from_pdf(content: bytes) -> str` - Extract text from PDF content
- `extract_text_from_docx(content: bytes) -> str` - Extract text from DOCX content
- `extract_text_from_pptx(content: bytes) -> str` - Extract text from PowerPoint content
- `extract_text_from_excel(content: bytes) -> str` - Extract text from Excel content
- `extract_text_from_file_langextract(content: bytes, file_type: str, filename: str) -> tuple[str, dict]` - Enhanced text extraction using LangExtract
- `extract_text_from_file(content: bytes, file_type: str, filename: str) -> str` - Backward compatible text extraction function

### Text Chunking
- `chunk_text_intelligent(elements: list, max_characters: int = 1000) -> List[dict]` - Intelligent chunking using LangExtract/Unstructured capabilities
- `chunk_text_basic(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]` - Basic text chunking
- `chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]` - Backward compatible chunking function

### Embedding Generation
- `generate_embeddings(text_chunks: list) -> dict` - Generate embeddings for text chunks using OpenAI
- `generate_embeddings_v2(texts: List[str]) -> List[List[float]]` - Generate embeddings using OpenAI (alternative implementation)

### Vector Storage (Legacy/Deprecated)
- `store_vault_embeddings_enhanced(project_uuid, user_uuid, file_id, text_chunks, embeddings, base_metadata, chunk_metadata_list)` - DEPRECATED: Legacy Agno storage function
- `store_vault_embeddings(project_uuid, user_uuid, file_id, text_chunks, embeddings, metadata)` - DEPRECATED: Legacy Agno storage function

### Vector Search
- `search_vault_embeddings(project_uuid, query_text, limit=10, file_ids=None, user_uuid=None) -> list` - Search for similar content in unified Vault vector database using LlamaIndex schema

### Database Management
- `get_database_connection()` - Get PostgreSQL database connection
- `ensure_vector_table_exists(table_name: str)` - Create vector table if it doesn't exist
- `store_embeddings(table_name, file_id, chunks, embeddings, metadata=None)` - Store text chunks and embeddings in vector database
- `search_similar_content_v2(table_name, query_text, limit=5, file_ids=None) -> List[Dict]` - Search for similar content using vector similarity (alternative implementation)

### AI Response Generation
- `generate_ai_response(question: str, context: str, prompt_type: str = "chat") -> dict` - Generate AI response using OpenAI GPT
- `generate_ai_response_stream(question: str, context: str, prompt_type: str = "chat")` - Generate streaming AI response using OpenAI GPT
- `generate_ai_response_v2(context: str, question: str) -> str` - Generate AI response using OpenAI (alternative implementation)

### Document Processing
- `index_documents(docs, source: str, vector_table_name: str, embed_model)` - Common indexing logic for documents
- `process_single_file(payload: FileIngestRequest)` - Process a single file for ingestion
- `process_vault_file_without_progress(payload: FileIngestRequest) -> int` - Process a vault file without progress tracking

### FastAPI Endpoints
- `lifespan(app: FastAPI)` - Startup and shutdown events for FastAPI app
- `ingest_gcs_docs(payload: IngestRequest)` - Ingest documents by GCS prefix (bulk mode)
- `ingest_single_file(payload: FileIngestRequest)` - Queue single file ingestion
- `delete_vectors(payload: DeleteVectorRequest)` - Delete vectors for a file
- `migrate_vault_vectors()` - Migrate vault vectors from old schema to new LlamaIndex-compatible schema
- `generate_ai_insights(payload: AiInsightsRequest)` - Generate AI insights for vault files based on a question
- `ai_chat(payload: AiChatRequest)` - Handle AI chat conversations about vault files
- `ai_chat_stream(payload: AiChatRequest)` - Handle AI chat conversations with streaming responses
- `generate_folder_summary(payload: FolderSummaryRequest)` - Generate AI summary for a folder's contents
- `analyze_file_content(file_id: int, analysis_type: str = "full")` - Analyze a specific file's content for insights
- `embed_vault_file(payload: VaultFileEmbedRequest)` - Embed a vault file for AI insights using unified LlamaIndex processing
- `root()` - Healthcheck route

## Classes

### Pydantic Models
- `Settings` - Settings object for progress updates with Django API
- `IngestRequest` - Request model for GCS bulk ingestion
- `FileIngestRequest` - Request model for single file ingestion
- `DeleteVectorRequest` - Request model for vector deletion
- `AiInsightsRequest` - Request model for AI insights
- `AiChatRequest` - Request model for AI chat conversations
- `FolderSummaryRequest` - Request model for folder summaries
- `VaultFileEmbedRequest` - Request model for vault file embedding

## Method Details

### Settings Class Methods
- `auth_headers` (property) - Return properly formatted auth headers for system API key
- `update_file_progress_sync(file_uuid, progress, processed_docs, total_docs, link_id=None, error=None)` - Update file ingestion progress
- `validate_auth_response(response)` - Validate authentication response and log helpful messages

### FileIngestRequest Class Methods
- `clean_file_path()` - Clean and validate the file path

## Summary
- **Total Functions**: 45 functions + 8 classes
- **FastAPI Endpoints**: 12 endpoints
- **Core Features**: File ingestion, vector storage, progress tracking, GCS integration, AI chat, text extraction, vault processing, streaming responses
