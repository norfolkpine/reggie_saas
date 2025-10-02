# Function Comparison: main.py vs main-logan.py

## Overview
- **main.py**: 8 functions + 4 classes (5 FastAPI endpoints)
- **main-logan.py**: 45 functions + 8 classes (12 FastAPI endpoints)

## Functions Present in Both Files

### Core Functions (Identical)
- `load_env(secret_id, env_file)` - Environment variable loading
- `get_vector_store(vector_table_name, current_embed_dim)` - Vector store management
- `index_documents(docs, source, vector_table_name, embed_model)` - Document indexing
- `process_single_file(payload)` - Single file processing
- `lifespan(app)` - FastAPI lifecycle management
- `root()` - Health check endpoint

### FastAPI Endpoints (Identical)
- `ingest_gcs_docs(payload)` - GCS bulk ingestion
- `ingest_single_file(payload)` - Single file ingestion
- `delete_vectors(payload)` - Vector deletion

### Classes (Identical)
- `Settings` - Progress tracking settings
- `IngestRequest` - GCS ingestion request model
- `FileIngestRequest` - Single file ingestion request model
- `DeleteVectorRequest` - Vector deletion request model

## Functions Only in main-logan.py

### Text Extraction & Processing (16 functions)
- `download_gcs_file(file_path)` - GCS file download
- `download_file_from_gcs(bucket_name, file_path)` - Alternative GCS download
- `extract_text_from_pdf_langextract(content)` - Enhanced PDF extraction
- `extract_text_from_docx_langextract(content)` - Enhanced DOCX extraction
- `extract_text_from_pptx_langextract(content)` - Enhanced PPTX extraction
- `extract_text_from_excel_langextract(content)` - Enhanced Excel extraction
- `extract_text_from_pdf_fallback(content)` - PDF fallback extraction
- `extract_text_from_docx_fallback(content)` - DOCX fallback extraction
- `extract_text_from_pptx_fallback(content)` - PPTX fallback extraction
- `extract_text_from_excel_fallback(content)` - Excel fallback extraction
- `extract_text_from_pdf(content)` - Basic PDF extraction
- `extract_text_from_docx(content)` - Basic DOCX extraction
- `extract_text_from_pptx(content)` - Basic PPTX extraction
- `extract_text_from_excel(content)` - Basic Excel extraction
- `extract_text_from_file_langextract(content, file_type, filename)` - Unified extraction
- `extract_text_from_file(content, file_type, filename)` - Backward compatible extraction

### Text Chunking (3 functions)
- `chunk_text_intelligent(elements, max_characters)` - Intelligent chunking
- `chunk_text_basic(text, chunk_size, overlap)` - Basic chunking
- `chunk_text(text, chunk_size, overlap)` - Backward compatible chunking

### Embedding Generation (2 functions)
- `generate_embeddings(text_chunks)` - OpenAI embeddings
- `generate_embeddings_v2(texts)` - Alternative embedding implementation

### Vector Storage & Search (6 functions)
- `store_vault_embeddings_enhanced(...)` - DEPRECATED: Legacy storage
- `store_vault_embeddings(...)` - DEPRECATED: Legacy storage
- `search_vault_embeddings(project_uuid, query_text, ...)` - Vault vector search
- `get_database_connection()` - Database connection
- `ensure_vector_table_exists(table_name)` - Table creation
- `store_embeddings(table_name, file_id, chunks, embeddings, metadata)` - Embedding storage
- `search_similar_content_v2(table_name, query_text, ...)` - Alternative search

### AI Response Generation (3 functions)
- `generate_ai_response(question, context, prompt_type)` - AI response generation
- `generate_ai_response_stream(question, context, prompt_type)` - Streaming AI responses
- `generate_ai_response_v2(context, question)` - Alternative AI response

### Vault Processing (2 functions)
- `ensure_vault_vector_table_exists()` - Vault table management
- `process_vault_file_without_progress(payload)` - Vault file processing

### Additional FastAPI Endpoints (7 endpoints)
- `migrate_vault_vectors()` - Schema migration
- `generate_ai_insights(payload)` - AI insights generation
- `ai_chat(payload)` - AI chat conversations
- `ai_chat_stream(payload)` - Streaming AI chat
- `generate_folder_summary(payload)` - Folder summaries
- `analyze_file_content(file_id, analysis_type)` - File content analysis
- `embed_vault_file(payload)` - Vault file embedding

### Additional Classes (4 classes)
- `AiInsightsRequest` - AI insights request model
- `AiChatRequest` - AI chat request model
- `FolderSummaryRequest` - Folder summary request model
- `VaultFileEmbedRequest` - Vault file embedding request model

## Key Differences

### main.py (Simpler)
- **Focus**: Basic file ingestion and vector storage
- **Features**: GCS integration, progress tracking, basic document processing
- **Size**: ~800 lines, minimal dependencies

### main-logan.py (Feature-Rich)
- **Focus**: Comprehensive document processing with AI capabilities
- **Features**: 
  - Advanced text extraction (PDF, DOCX, PPTX, Excel)
  - AI chat and insights generation
  - Streaming responses
  - Vault file processing
  - Multiple embedding strategies
  - Intelligent text chunking
- **Size**: ~2,700 lines, extensive dependencies

## Migration Considerations

### From main.py to main-logan.py
- ✅ **Compatible**: All core functions are present
- ✅ **Enhanced**: Additional features available
- ⚠️ **Dependencies**: Requires additional libraries (PyPDF2, python-docx, etc.)
- ⚠️ **Size**: Significantly larger codebase

### From main-logan.py to main.py
- ❌ **Loss of Features**: AI capabilities, advanced text extraction, vault processing
- ❌ **Breaking Changes**: Missing endpoints and functionality
- ✅ **Simpler**: Reduced complexity and dependencies

## Recommendation
**main-logan.py** appears to be the more complete and feature-rich version, suitable for production use with comprehensive document processing and AI capabilities. **main.py** seems to be a simplified version, possibly for basic use cases or as a starting point.
