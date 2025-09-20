# Text Extraction for Agent in apps/reggie

This document describes the two primary locations where text extraction is handled for the agent in the `apps/reggie` directory.

## 1. Main File Reader Tool - `apps/reggie/agents/tools/filereader.py`

This is the core text extraction module that handles multiple file formats and provides the primary text extraction functionality for the agent.

### Key Components

#### File Type Detection
The `detect_file_type()` function automatically detects file types using:
- MIME type mapping for common formats
- File extension fallback
- Support for: PDF, CSV, DOCX, JSON, Markdown, TXT

#### FileReaderTools Class
The main class that provides text extraction capabilities:

```python
class FileReaderTools(Toolkit):
    def __init__(self):
        super().__init__(name="file_reader_tools")
        self.register(self.read_file)
```

### Supported File Formats

| Format | Library Used | Extraction Method |
|--------|-------------|-------------------|
| **PDF** | `pypdf` | Page-by-page text extraction with error handling |
| **CSV** | `pandas` | DataFrame to string conversion (max 100 rows) |
| **DOCX** | `python-docx` | Paragraph text extraction |
| **TXT** | Built-in | Multiple encoding support (UTF-8, Latin-1, CP1252, ISO-8859-1) |
| **JSON** | Built-in | Pretty-printed JSON output |
| **Markdown** | Built-in | Direct UTF-8 decoding |

### Key Features

- **Error Handling**: Graceful fallbacks for unsupported formats
- **Character Limits**: Configurable max character limits (default: 20,000)
- **Multiple Encodings**: Automatic encoding detection for text files
- **Temporary File Handling**: Safe temporary file creation for PDF/DOCX processing
- **Page-by-Page Extraction**: For PDFs, extracts text from each page separately with page markers

### Main Methods

#### `read_file(content, file_type, file_name, max_chars=20000)`
Primary extraction method that:
1. Detects file type automatically
2. Processes content based on detected type
3. Handles errors gracefully
4. Truncates content if exceeding max_chars

#### `read_file_bytes(file_bytes, file_type, file_name, max_chars=20000)`
Alternative method for byte input with similar functionality.

### PDF Processing Details
```python
# PDF extraction with page-by-page processing
with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
    tmp.write(content)
    tmp.flush()
    pdf_reader = pypdf.PdfReader(file)
    for page_num, page in enumerate(pdf_reader.pages, 1):
        page_text = page.extract_text()
        if page_text and page_text.strip():
            text_content.append(f"--- Page {page_num} ---\n{page_text}")
```

## 2. Real-time Agent Processing - `apps/reggie/consumers.py`

This handles text extraction for ephemeral files during live agent conversations in the `StreamAgentConsumer` class.

### Processing Flow

The text extraction happens in the `handle()` method of `StreamAgentConsumer` (lines 156-180):

```python
# Process files asynchronously if we have any
if ephemeral_files:
    reader_tool = FileReaderTools()
    extracted_texts = []
    attachments = []
    for ephemeral_file in ephemeral_files:
        file_type = getattr(ephemeral_file, "mime_type", None) or None
        file_name = getattr(ephemeral_file, "name", None) or None
        with ephemeral_file.file.open("rb") as f:
            file_bytes = f.read()
        # Extract text using the tool, always pass file_type and file_name
        text = reader_tool.read_file(content=file_bytes, file_type=file_type, file_name=file_name)
        extracted_texts.append(f"\n--- File: {ephemeral_file.name} ({file_type}) ---\n{text}")
```

### Key Features

- **Asynchronous Processing**: Files are processed asynchronously to avoid blocking
- **Session-based**: Only processes files associated with the current session
- **Metadata Preservation**: Maintains file metadata (UUID, name, MIME type, URL)
- **LLM Integration**: Extracted text is prepended to user messages for LLM processing
- **Attachment Tracking**: Builds attachment metadata for reference

### Integration with Agent

The extracted text is integrated into the agent's input as follows:

```python
# Prepend extracted file text to user message for LLM input
if extracted_texts:
    llm_input = "\n\n".join(extracted_texts) + "\n\n" + (message if message else "")
```

### Performance Considerations

- **Timing Logs**: Includes performance timing for file processing
- **Database Optimization**: Uses `only()` to fetch only required fields
- **Memory Management**: Processes files one at a time to manage memory usage

## Usage Patterns

### For Real-time Conversations
1. User uploads files during chat session
2. Files are stored as `EphemeralFile` objects
3. `StreamAgentConsumer` processes files when user sends message
4. Extracted text is combined with user message
5. Combined input is sent to LLM

### For Knowledge Base Ingestion
1. Files are processed through `FileReaderTools` directly
2. Extracted text is used for embedding generation
3. Text chunks are stored in vector database
4. Files can be referenced later for retrieval

## Dependencies

The text extraction system requires the following optional dependencies:
- `pypdf` for PDF processing
- `pandas` for CSV processing  
- `python-docx` for DOCX processing

These are imported with try/except blocks to handle cases where they're not available.
