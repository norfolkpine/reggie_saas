import os
import json
from typing import Optional
from agno.tools import Toolkit

# Try to import agno readers if available
try:
    from agno.document.reader.pdf_reader import PDFReader
except ImportError:
    PDFReader = None
try:
    from agno.document.reader.csv_reader import CSVReader
except ImportError:
    CSVReader = None
try:
    from agno.document.reader.text_reader import TextReader
except ImportError:
    TextReader = None

# DOCX
try:
    import docx
except ImportError:
    docx = None

# Markdown
try:
    import markdown
except ImportError:
    markdown = None

class FileReaderTools(Toolkit):
    def __init__(self):
        super().__init__(name="file_reader_tools")
        self.register(self.read_file)

    def read_file(self, content: bytes, file_type: Optional[str] = None, max_chars: int = 20000) -> str:
        """
        Extract text from a file given as bytes. Supports PDF, DOCX, CSV, TXT, JSON, and Markdown.
        Args:
            content: File bytes
            file_type: Optional file type (pdf, docx, csv, txt, json, md)
            max_chars: Maximum number of characters to return (default 20,000)
        Returns:
            Extracted text content (truncated if too long)
        """
        import io
        ext = (file_type or "").lower()
        try:
            if ext == "pdf" and PDFReader:
                reader = PDFReader()
                docs = reader.read(io.BytesIO(content))
                text = "\n".join(doc.content for doc in docs)
            elif ext == "csv" and CSVReader:
                reader = CSVReader()
                docs = reader.read(io.BytesIO(content))
                text = "\n".join(doc.content for doc in docs)
            elif ext == "txt" and TextReader:
                reader = TextReader()
                docs = reader.read(io.BytesIO(content))
                text = "\n".join(doc.content for doc in docs)
            elif ext == "docx" and docx:
                doc = docx.Document(io.BytesIO(content))
                text = "\n".join([para.text for para in doc.paragraphs])
            elif ext == "json":
                data = json.loads(content.decode("utf-8"))
                text = json.dumps(data, indent=2)
            elif ext in ("md", "markdown"):
                md_text = content.decode("utf-8")
                text = md_text
            else:
                # Fallback: try to decode as utf-8 text
                text = content.decode("utf-8")
            if len(text) > max_chars:
                return text[:max_chars] + "\n... [truncated]"
            return text
        except Exception as e:
            return f"Error reading file: {e}"

    def read_file_bytes(self, file_bytes: bytes, file_type: Optional[str] = None, max_chars: int = 20000) -> str:
        """
        Read and extract text from file bytes. Supports PDF, DOCX, CSV, TXT, JSON, and Markdown.
        Args:
            file_bytes: File content as bytes
            file_type: Optional file type (pdf, docx, csv, txt, json, md, mime types)
            max_chars: Maximum number of characters to return (default 20,000)
        Returns:
            Extracted text content (truncated if too long)
        """
        import io
        ftype = (file_type or "").lower()
        try:
            if (ftype == "pdf" or "pdf" in ftype) and PDFReader:
                # PDFReader expects a file path, so we need to write to a temp file
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                    tmp.write(file_bytes)
                    tmp.flush()
                    docs = PDFReader().read(tmp.name)
                    text = "\n".join(doc.content for doc in docs)
            elif (ftype == "csv" or "csv" in ftype) and CSVReader:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".csv", delete=True) as tmp:
                    tmp.write(file_bytes)
                    tmp.flush()
                    docs = CSVReader().read(tmp.name)
                    text = "\n".join(doc.content for doc in docs)
            elif (ftype == "txt" or "plain" in ftype):
                text = file_bytes.decode("utf-8", errors="replace")
            elif (ftype == "docx" or "word" in ftype) and docx:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".docx", delete=True) as tmp:
                    tmp.write(file_bytes)
                    tmp.flush()
                    doc = docx.Document(tmp.name)
                    text = "\n".join([para.text for para in doc.paragraphs])
            elif (ftype == "json" or "json" in ftype):
                text = file_bytes.decode("utf-8", errors="replace")
                data = json.loads(text)
                text = json.dumps(data, indent=2)
            elif ftype in ("md", "markdown") or "markdown" in ftype:
                text = file_bytes.decode("utf-8", errors="replace")
            else:
                # Fallback: try to decode as text
                text = file_bytes.decode("utf-8", errors="replace")
            if len(text) > max_chars:
                return text[:max_chars] + "\n... [truncated]"
            return text
        except Exception as e:
            return f"Error reading file from bytes: {e}" 