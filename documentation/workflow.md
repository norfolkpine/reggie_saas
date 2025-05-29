# Knowledge Base and File Upload Workflow

This document outlines the process for creating a knowledge base and uploading files for ingestion.

## 1. Creating a Knowledge Base

A knowledge base is a container for your documents that allows for efficient storage and retrieval of information. Here's how to create one:

### Knowledge Base Properties

- `name`: A unique identifier for your knowledge base
- `knowledge_type`: The type of knowledge base, which can be:
  - `pdf`: Local PDF Files
  - `document`: Document Files (DOCX)
  - `csv`: CSV Files
  - `json`: JSON Files
  - `text`: Local Text Files
  - `website`: Website Data
  - `pdf_url`: PDF Files from URLs
  - `s3_pdf`: PDF Files from S3
  - `s3_text`: Text Files from S3
  - And more...
- `vector_table_name`: A unique name for the vector database table that will store embeddings
- `path`: Optional path for files or storage location

## 2. File Upload Process

### Supported File Types

The system supports the following file types:
- PDF (`.pdf`)
- Word Documents (`.docx`)
- Text Files (`.txt`)
- CSV Files (`.csv`)
- JSON Files (`.json`)

### Upload Methods

#### A. Using the UI Component

The system provides a modern drag-and-drop interface for file uploads:

1. Drag files into the upload area or click to select files
2. Choose whether to auto-ingest files
3. If auto-ingest is enabled, select the target knowledge base
4. Upload the files
5. Monitor the ingestion status

#### B. Using the API

You can also upload files programmatically using the API:

```typescript
// Example using the fileService
const fileService = new FileService();
const response = await fileService.uploadFiles(files, {
  autoIngest: true,
  knowledgeBaseId: 123,
  teamId: 456, // Optional
  isGlobal: false,
  visibility: 'private'
});
```

### File Properties

Each uploaded file includes:
- Basic information (title, description, file type)
- Storage details (GCS path)
- Knowledge base association
- Ingestion status and progress
- Visibility settings (public/private)
- Team association (optional)

## 3. Ingestion Process

### Auto-Ingestion

When auto-ingestion is enabled:

1. File is uploaded to cloud storage
2. System initiates the ingestion process
3. File content is processed and embedded
4. Embeddings are stored in the vector database
5. Progress is tracked and updated in real-time

### Manual Ingestion

For files not auto-ingested:

1. Select the files to ingest
2. Choose the target knowledge base
3. Trigger ingestion through the UI or API
4. Monitor ingestion progress

### Ingestion Status

Files can have the following ingestion statuses:
- `pending`: Waiting to be processed
- `processing`: Currently being ingested
- `completed`: Successfully ingested
- `failed`: Ingestion failed (error message provided)

### Progress Tracking

The system tracks:
- Overall ingestion progress (0-100%)
- Number of processed documents
- Total documents to process
- Start and completion timestamps

## 4. Error Handling

The system provides comprehensive error handling:

- File type validation
- Upload size limits
- Knowledge base validation
- Ingestion process monitoring
- Detailed error messages
- Retry capabilities for failed ingestions

## 5. Best Practices

1. **File Organization**
   - Use descriptive file names
   - Group related files in the same knowledge base
   - Consider team-specific knowledge bases for better organization

2. **Ingestion Strategy**
   - Enable auto-ingestion for immediate processing
   - Use batch uploads for multiple files
   - Monitor ingestion status for large files

3. **Security**
   - Set appropriate file visibility
   - Use team-specific knowledge bases when needed
   - Follow proper API key management practices

4. **Performance**
   - Upload files in reasonable batch sizes
   - Monitor ingestion progress for large files
   - Consider file size and type when planning uploads

## 6. Troubleshooting

Common issues and solutions:

1. **Upload Failures**
   - Check file type and size
   - Verify network connection
   - Ensure proper permissions

2. **Ingestion Failures**
   - Check file format and content
   - Verify knowledge base configuration
   - Review error messages in logs

3. **Performance Issues**
   - Reduce batch size
   - Check system resources
   - Monitor ingestion queue 