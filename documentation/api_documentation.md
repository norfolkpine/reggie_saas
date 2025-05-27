# File Processing API Documentation

## Overview
This document describes the API endpoints for file processing, including upload, ingestion, and progress tracking functionalities.

## Authentication
All endpoints require authentication via Bearer token except where noted. Include the token in the Authorization header:
```
Authorization: Bearer <your_token>
```

## 1. Upload Files
**Endpoint:** `POST /api/v1/files/`

Upload one or more documents to the system with optional auto-ingestion into a knowledge base.

### Request
- Content-Type: `multipart/form-data`

#### Parameters
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| files[] | File Array | Yes | One or more files to upload. Supports PDF, DOCX, TXT, CSV, and JSON |
| title | String | No | Optional title for the files (defaults to filename) |
| description | String | No | Optional description for the files |
| team | Integer | No | Optional team ID. Can be null. Value of 0 or invalid IDs treated as null |
| auto_ingest | Boolean | No | Whether to automatically ingest the files |
| is_global | Boolean | No | Upload to global library (superadmins only). Default: false |
| knowledgebase_id | String | No* | Knowledge base ID (e.g. "kbo-8df45f-llamaindex-t"). Required if auto_ingest is true |

### Response
#### Success (201)
```json
{
    "message": "Successfully uploaded 2 documents",
    "documents": [
        {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "title": "example.pdf",
            "description": "Sample document",
            "file_type": "pdf",
            "storage_path": "path/to/file",
            "is_global": false
        }
    ],
    "failed_uploads": []
}
```

#### Error (400)
```json
{
    "error": "No files provided"
    // or
    "error": "knowledgebase_id is required when auto_ingest is True"
    // or
    "error": "Knowledge base with ID 'kbo-invalid' does not exist"
}
```

## 2. Ingest Selected Files
**Endpoint:** `POST /api/v1/files/ingest-selected/`

Ingest multiple files into a knowledge base.

### Request
```json
{
    "file_ids": [1, 2, 3],
    "knowledgebase_id": "kbo-8df45f-llamaindex-t"
}
```

### Response
#### Success (200)
```json
{
    "message": "Started ingestion for 3 files",
    "links": [
        {
            "file_id": 1,
            "knowledge_base_id": "kbo-8df45f-llamaindex-t",
            "status": "processing"
        }
    ]
}
```

## 3. Update Ingestion Progress
**Endpoint:** `POST /api/v1/files/{uuid}/update-progress/`

Update the ingestion progress for a file. Used internally by the ingestion service.

**Note:** This endpoint does not require authentication as it's called internally by the Cloud Run service.

### Request
```json
{
    "progress": 75.5,
    "processed_docs": 15,
    "total_docs": 20,
    "file_size": 1024000,
    "page_count": 20,
    "embedding_model": "text-embedding-ada-002",
    "chunk_size": 1000,
    "chunk_overlap": 200
}
```

### Response
#### Success (200)
```json
{
    "status": "success",
    "message": "Progress updated"
}
```

## 4. Reingest File
**Endpoint:** `POST /api/v1/files/{uuid}/reingest/`

Reingest a file into its associated knowledge bases.

### Request
Empty POST request

### Response
#### Success (200)
```json
{
    "message": "Started reingestion for file",
    "status": "processing"
}
```

## Notes
- Authentication is required for all endpoints except update-progress
- Files can be linked to multiple knowledge bases
- Progress tracking is available for each file ingestion
- Supports various file types including PDF, DOCX, TXT, CSV, and JSON
- Global library uploads are restricted to superadmins
- Each file gets a unique UUID for tracking and reference

## Error Handling
Common error responses:
- 400: Bad Request (validation errors)
- 401: Unauthorized (missing authentication)
- 403: Forbidden (insufficient permissions)
- 404: Not Found (invalid UUID or resource)
- 500: Internal Server Error (processing failures)

## Data Models

### File Model
```json
{
    "uuid": "string",
    "title": "string",
    "description": "string",
    "file_type": "string",
    "storage_path": "string",
    "original_path": "string",
    "uploaded_by": "integer",
    "team": "integer",
    "source": "string",
    "visibility": "string",
    "is_global": "boolean",
    "created_at": "datetime",
    "updated_at": "datetime"
}
```

### FileKnowledgeBaseLink Model
```json
{
    "file": "File object reference",
    "knowledge_base": "KnowledgeBase object reference",
    "ingestion_status": "string (not_started|processing|completed|failed)",
    "ingestion_progress": "float (0-100)",
    "processed_docs": "integer",
    "total_docs": "integer",
    "embedding_model": "string",
    "chunk_size": "integer",
    "chunk_overlap": "integer"
}
``` 