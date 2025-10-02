# File Upload and Ingestion Process

## Overview

The file upload and ingestion system provides a robust way to manage documents and their ingestion into knowledge bases. The system supports multiple file types, team-based access control, and progress tracking for ingestion.

## File Types and Storage

### Supported File Types
- PDF (`.pdf`)
- Microsoft Word (`.docx`)
- Text (`.txt`)
- CSV (`.csv`)
- JSON (`.json`)

### Storage Structure
Files are stored in Google Cloud Storage (GCS) with the following path structure:
- User files: `bh-opie-media/user_files/{user_id}-{user_uuid}/YYYY/MM/DD/`
- Global files: `bh-opie-media/global/library/YYYY/MM/DD/`

## Upload Process

### API Endpoint
```
POST /api/files/
```

### Features
- Single or multiple file upload support
- Optional auto-ingestion into knowledge base
- Progress tracking for ingestion
- Team and visibility settings
- Global library uploads (superadmins only)

### Upload Request Parameters
- `files`: One or more files to upload (required)
- `title`: Optional title for the files (defaults to filename)
- `description`: Optional description for the files
- `team`: Optional team ID (can be null)
- `auto_ingest`: Whether to automatically ingest the files
- `is_global`: Upload to global library (superadmins only)
- `knowledgebase_id`: Required if auto_ingest is True

### Upload Response
```json
{
    "message": "2 documents uploaded successfully.",
    "documents": [
        {
            "id": 1,
            "title": "document1.pdf",
            "file_type": "pdf",
            "ingestion_status": "processing",
            "ingestion_progress": 0.0
        }
    ],
    "failed_uploads": []
}
```

## Ingestion Process

### Ingestion States
- `not_started`: Initial state
- `pending`: Queued for ingestion
- `processing`: Currently being ingested
- `completed`: Successfully ingested
- `failed`: Ingestion failed

### Auto-Ingestion
When `auto_ingest=True`:
1. File is uploaded to GCS
2. System creates a FileKnowledgeBaseLink
3. Cloud Run ingestion service is called
4. Progress is tracked through webhook updates

### Manual Ingestion
Files can be manually ingested using:
1. Admin interface: Use the "Retry ingestion" action
2. API endpoint: `POST /api/files/ingest-selected/`

### Progress Tracking
The system tracks:
- Overall progress percentage
- Number of processed documents
- Total documents to process
- Start and completion times
- Error messages (if any)

## Access Control

### File Visibility
- `private`: Only accessible by the uploader and team members
- `public`: Accessible by all authenticated users
- `global`: System-wide files (managed by superadmins)

### Permissions
- `can_ingest_files`: Required for ingestion operations
- `can_manage_global_files`: Required for global library management

## Error Handling

### Common Error Scenarios
1. Unsupported file type
2. Invalid knowledge base ID
3. Missing required permissions
4. Storage service unavailable
5. Ingestion service failure

### Error Response Format
```json
{
    "error": "Error message",
    "details": "Detailed error information"
}
```

## Best Practices

1. **File Naming**
   - Use descriptive file names
   - Avoid special characters
   - Keep filenames reasonably short

2. **Ingestion**
   - Use auto-ingestion for immediate processing
   - Monitor ingestion progress for large files
   - Check error messages if ingestion fails

3. **Team Management**
   - Organize files by team when possible
   - Use appropriate visibility settings
   - Maintain clear file descriptions

4. **Performance**
   - Batch upload multiple files when possible
   - Consider file size limitations
   - Monitor ingestion progress for large files

## Troubleshooting

### Common Issues

1. **Upload Failures**
   - Check file size limits
   - Verify file type support
   - Ensure proper permissions

2. **Ingestion Failures**
   - Check knowledge base configuration
   - Verify file format integrity
   - Monitor ingestion service logs

3. **Access Issues**
   - Verify team membership
   - Check file visibility settings
   - Confirm user permissions

### Debug Tools

1. **Admin Interface**
   - View file details
   - Track ingestion status
   - Retry failed ingestions

2. **API Endpoints**
   - Check file status
   - Monitor ingestion progress
   - View error details