from typing import List, Optional, Any, Union
from pathlib import Path
import re
import csv
import io
import tempfile
import urllib.parse
from urllib.parse import urlparse

# Import required packages
try:
    from agno.tools import Toolkit, tool
    AGNO_AVAILABLE = True
except ImportError:
    AGNO_AVAILABLE = False

# Document processing libraries
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Google Cloud Storage support
try:
    from google.cloud import storage
    from google.auth import default
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


class DocumentReaderTools(Toolkit):
    """
    Toolkit for reading various document formats including PDF, Excel, CSV, DOCX, and text files.
    Supports both local files and GCP URLs.
    """
    
    def __init__(self, files: Optional[List[Union[str, Path]]] = None, **kwargs):
        """
        Initialize the DocumentReaderTools toolkit.
        
        Args:
            files: List of file paths or GCP URLs to be available for reading
        """
        self.files = []
        self.temp_files = []  # Track temporary files for cleanup
        
        if files:
            for f in files:
                if isinstance(f, str) and (f.startswith('http') or f.startswith('gs://')):
                    # Handle URLs and GCP paths
                    self.files.append(f)
                else:
                    # Handle local paths
                    self.files.append(Path(f) if isinstance(f, str) else f)
        
        # Prepare file paths for reading (download GCS files to temp locations)
        self.processed_files = self._prepare_file_paths_for_reading()
        
        super().__init__(
            name="document_reader_tools", 
            tools=[
                self.list_available_files,
                self.read_document,
                self.get_supported_formats,
                self.read_pdf_file,
                self.read_excel_file,
                self.read_csv_file,
                self.read_docx_file,
                self.read_text_file,
                self.download_gcp_file
            ], 
            **kwargs
        )

    def _is_gcp_url(self, file_path: Union[str, Path]) -> bool:
        """Check if the file path is a GCP URL."""
        if isinstance(file_path, str):
            return file_path.startswith('gs://') or file_path.startswith('https://storage.googleapis.com/')
        return False

    def _download_gcp_file(self, file_path: str) -> Optional[Path]:
        """Download file from GCP URL to temporary location."""
        if not HTTPX_AVAILABLE:
            return None
        
        try:
            # Convert gs:// URL to https:// URL if needed
            if file_path.startswith('gs://'):
                # Convert gs://bucket/path to https://storage.googleapis.com/bucket/path
                parts = file_path[5:].split('/', 1)
                if len(parts) == 2:
                    bucket, path = parts
                    file_path = f"https://storage.googleapis.com/{bucket}/{path}"
            
            # Try authenticated download first (for private buckets)
            if GCS_AVAILABLE and file_path.startswith('https://storage.googleapis.com/'):
                temp_path = self._download_gcs_authenticated(file_path)
                if temp_path:
                    return temp_path
            
            # Fallback to public HTTPS download
            return self._download_public_https(file_path)
                
        except Exception as e:
            print(f"Error downloading file from {file_path}: {e}")
            return None

    def _download_gcs_authenticated(self, https_url: str) -> Optional[Path]:
        """Download file from GCS using authenticated client (for private buckets)."""
        try:
            # Parse URL to get bucket and blob path
            # https://storage.googleapis.com/bucket-name/path/to/file
            url_parts = https_url.replace('https://storage.googleapis.com/', '').split('/', 1)
            if len(url_parts) != 2:
                return None
            
            bucket_name, blob_path = url_parts
            
            # Initialize GCS client with default credentials
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=self._get_file_extension(https_url))
            
            # Download blob to temporary file
            blob.download_to_filename(temp_file.name)
            temp_file.close()
            
            self.temp_files.append(temp_file.name)
            return Path(temp_file.name)
            
        except Exception as e:
            print(f"Error downloading with GCS authentication: {e}")
            return None

    def _download_public_https(self, file_path: str) -> Optional[Path]:
        """Download file using public HTTPS (for public buckets)."""
        try:
            # Download file
            with httpx.Client() as client:
                response = client.get(file_path, timeout=30.0)
                response.raise_for_status()
                
                # Create temporary file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=self._get_file_extension(file_path))
                temp_file.write(response.content)
                temp_file.close()
                
                self.temp_files.append(temp_file.name)
                return Path(temp_file.name)
                
        except Exception as e:
            print(f"Error downloading with public HTTPS: {e}")
            return None

    def _get_file_extension(self, file_path: str) -> str:
        """Extract file extension from URL or path."""
        # Try to get extension from URL path
        parsed = urlparse(file_path)
        path = parsed.path
        if '.' in path:
            return '.' + path.split('.')[-1]
        
        # Fallback extensions based on content type or common patterns
        if 'pdf' in file_path.lower():
            return '.pdf'
        elif any(ext in file_path.lower() for ext in ['.xlsx', '.xls']):
            return '.xlsx'
        elif 'csv' in file_path.lower():
            return '.csv'
        elif 'docx' in file_path.lower():
            return '.docx'
        else:
            return '.txt'

    def _get_file_path(self, file_name: str) -> Optional[Path]:
        """Get file path, using processed files (downloaded from GCP if necessary)."""
        # First check processed files (which include downloaded GCS files)
        for file_path in self.processed_files:
            if isinstance(file_path, Path):
                if file_path.name == file_name:
                    return file_path
        
        # Fallback to original files if not found in processed files
        for file_path in self.files:
            if isinstance(file_path, str):
                # Handle URL/GCP path
                if self._is_gcp_url(file_path):
                    # Extract filename from URL
                    url_filename = file_path.split('/')[-1]
                    if url_filename == file_name or file_name in file_path:
                        return self._download_gcp_file(file_path)
                else:
                    # Local file path as string
                    if Path(file_path).name == file_name:
                        return Path(file_path)
            else:
                # Local Path object
                if file_path.name == file_name:
                    return file_path
        return None

    def _prepare_file_paths_for_reading(self) -> List[Union[str, Path]]:
        """
        Prepare file paths for reading, handling both local files and GCS URLs.
        This method processes ephemeral files that might have GCS URLs.
        """
        processed_paths = []
        
        for file_path in self.files:
            if isinstance(file_path, str):
                if self._is_gcp_url(file_path):
                    # For GCS URLs, download to temp file first
                    temp_path = self._download_gcp_file(file_path)
                    if temp_path:
                        processed_paths.append(temp_path)
                    else:
                        print(f"[DocumentReaderTools] Failed to download GCS file: {file_path}")
                else:
                    # Local file path
                    processed_paths.append(Path(file_path))
            else:
                # Path object (local file)
                processed_paths.append(file_path)
        
        return processed_paths

    def list_available_files(self) -> str:
        """
        Lists all available files that can be read.
        
        Returns:
            str: List of available files with their formats
        """
        if not self.files and not self.processed_files:
            return "No files are currently available for reading."
        
        file_info = []
        
        # Show processed files (downloaded from GCS)
        if self.processed_files:
            file_info.append("=== Processed Files (Ready for Reading) ===")
            for file_path in self.processed_files:
                if isinstance(file_path, Path):
                    if file_path.exists():
                        file_info.append(f"- {file_path.name} ({file_path.suffix.upper()}) - Downloaded from GCS")
                    else:
                        file_info.append(f"- {file_path.name} (NOT FOUND)")
        
        # Show original files
        if self.files:
            file_info.append("\n=== Original Files ===")
            for file_path in self.files:
                if isinstance(file_path, str) and self._is_gcp_url(file_path):
                    # GCP URL
                    file_info.append(f"- {file_path} (GCS URL)")
                elif isinstance(file_path, Path):
                    # Local file
                    if file_path.exists():
                        file_info.append(f"- {file_path.name} ({file_path.suffix.upper()})")
                    else:
                        file_info.append(f"- {file_path.name} (NOT FOUND)")
                else:
                    # String path
                    path_obj = Path(file_path)
                    if path_obj.exists():
                        file_info.append(f"- {path_obj.name} ({path_obj.suffix.upper()})")
                    else:
                        file_info.append(f"- {path_obj.name} (NOT FOUND)")
        
        return "\n".join(file_info)

    def get_supported_formats(self) -> str:
        """
        Returns a list of supported file formats.
        
        Returns:
            str: List of supported formats
        """
        formats = [
            "PDF (.pdf) - Text extraction from PDF documents",
            "Excel (.xlsx, .xls) - Data from Excel spreadsheets",
            "CSV (.csv) - Tabular data from CSV files",
            "DOCX (.docx) - Text from Word documents",
            "Text (.txt, .md, .json, .xml, .html, .htm) - Plain text files",
            "GCP URLs (gs:// or https://storage.googleapis.com/) - Remote files from Google Cloud Storage"
        ]
        return "Supported file formats:\n" + "\n".join(f"- {fmt}" for fmt in formats)

    def download_gcp_file(self, file_url: str) -> str:
        """
        Downloads a file from GCP URL and returns information about the download.
        
        Args:
            file_url: GCP URL to download
            
        Returns:
            str: Download status and file information
        """
        if not HTTPX_AVAILABLE:
            return "Error: httpx library not available for downloading files"
        
        # Check if GCS authentication is available
        auth_status = self._check_gcs_auth_status()
        
        temp_path = self._download_gcp_file(file_url)
        if temp_path:
            return f"Successfully downloaded file from {file_url} to temporary location: {temp_path}\nAuthentication: {auth_status}"
        else:
            return f"Failed to download file from {file_url}\nAuthentication: {auth_status}"

    def _check_gcs_auth_status(self) -> str:
        """Check if GCS authentication is available."""
        if not GCS_AVAILABLE:
            return "GCS library not available - using public HTTPS only"
        
        try:
            # Try to get default credentials
            credentials, project = default()
            if credentials:
                return "GCS authentication available - can access private buckets"
            else:
                return "No GCS credentials found - using public HTTPS only"
        except Exception as e:
            return f"GCS authentication error: {e} - using public HTTPS only"

    def read_document(self, file_name: str, chunk_size: int = 512, chunk_overlap: int = 50) -> str:
        """
        Reads a document and returns its content in chunks.
        
        Args:
            file_name: Name of the file to read
            chunk_size: Size of each text chunk
            chunk_overlap: Overlap between chunks
            
        Returns:
            str: Document content in chunks
        """
        # Get file path (download from GCP if necessary)
        target_file = self._get_file_path(file_name)
        
        if not target_file:
            return f"File '{file_name}' not found in available files."
        
        if not target_file.exists():
            return f"File '{file_name}' does not exist or is not accessible."
        
        # Read content based on file type
        content = self._read_document_content(target_file)
        if content.startswith("Error:"):
            return content
        
        # Chunk the content
        chunks = self._chunk_text(content, chunk_size, chunk_overlap)
        
        # Format output
        result = f"Document: {file_name}\n"
        result += f"Format: {target_file.suffix.upper()}\n"
        result += f"Total chunks: {len(chunks)}\n\n"
        result += "Content chunks:\n" + "\n---\n".join(chunks)
        
        return result

    def read_pdf_file(self, file_name: str) -> str:
        """
        Reads a PDF file and extracts text content.
        
        Args:
            file_name: Name of the PDF file to read
            
        Returns:
            str: Extracted text content from PDF
        """
        if not PYPDF_AVAILABLE:
            return "Error: PyPDF library not available for reading PDF files"
        
        # Get file path (download from GCP if necessary)
        target_file = self._get_file_path(file_name)
        
        if not target_file:
            return f"PDF file '{file_name}' not found in available files."
        
        try:
            text_content = []
            with open(target_file, 'rb') as file:
                pdf_reader = pypdf.PdfReader(file)
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    try:
                        page_text = page.extract_text()
                        if page_text.strip():
                            text_content.append(f"--- Page {page_num} ---\n{page_text}")
                    except Exception as e:
                        text_content.append(f"--- Page {page_num} (Error: {e}) ---\n")
            
            return "\n\n".join(text_content) if text_content else "No text content found in PDF"
        except Exception as e:
            return f"Error reading PDF file {file_name}: {e}"

    def read_excel_file(self, file_name: str, sheet_name: Optional[str] = None) -> str:
        """
        Reads an Excel file and extracts data.
        
        Args:
            file_name: Name of the Excel file to read
            sheet_name: Specific sheet to read (optional)
            
        Returns:
            str: Extracted data from Excel file
        """
        if not PANDAS_AVAILABLE:
            return "Error: Pandas library not available for reading Excel files"
        
        # Get file path (download from GCP if necessary)
        target_file = self._get_file_path(file_name)
        
        if not target_file:
            return f"Excel file '{file_name}' not found in available files."
        
        try:
            if sheet_name:
                # Read specific sheet
                df = pd.read_excel(target_file, sheet_name=sheet_name)
                if not df.empty:
                    return f"--- Sheet: {sheet_name} ---\n{df.to_string(index=False, max_rows=100)}"
                else:
                    return f"No content found in sheet '{sheet_name}'"
            else:
                # Read all sheets
                excel_file = pd.ExcelFile(target_file)
                content_parts = []
                
                for sheet in excel_file.sheet_names:
                    try:
                        df = pd.read_excel(target_file, sheet_name=sheet)
                        if not df.empty:
                            sheet_content = f"--- Sheet: {sheet} ---\n"
                            sheet_content += df.to_string(index=False, max_rows=100)
                            content_parts.append(sheet_content)
                    except Exception as e:
                        content_parts.append(f"--- Sheet: {sheet} (Error: {e}) ---\n")
                
                return "\n\n".join(content_parts) if content_parts else "No content found in Excel file"
        except Exception as e:
            return f"Error reading Excel file {file_name}: {e}"

    def read_csv_file(self, file_name: str) -> str:
        """
        Reads a CSV file and extracts data.
        
        Args:
            file_name: Name of the CSV file to read
            
        Returns:
            str: Extracted data from CSV file
        """
        if not PANDAS_AVAILABLE:
            return "Error: Pandas library not available for reading CSV files"
        
        # Get file path (download from GCP if necessary)
        target_file = self._get_file_path(file_name)
        
        if not target_file:
            return f"CSV file '{file_name}' not found in available files."
        
        try:
            df = pd.read_csv(target_file)
            if not df.empty:
                return f"--- CSV Content ---\n{df.to_string(index=False, max_rows=100)}"
            else:
                return "No content found in CSV file"
        except Exception as e:
            return f"Error reading CSV file {file_name}: {e}"

    def read_docx_file(self, file_name: str) -> str:
        """
        Reads a DOCX file and extracts text content.
        
        Args:
            file_name: Name of the DOCX file to read
            
        Returns:
            str: Extracted text content from DOCX file
        """
        # Get file path (download from GCP if necessary)
        target_file = self._get_file_path(file_name)
        
        if not target_file:
            return f"DOCX file '{file_name}' not found in available files."
        
        try:
            from docx import Document
            doc = Document(target_file)
            text_content = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_content.append(paragraph.text)
            return "\n".join(text_content) if text_content else "No text content found in DOCX file"
        except ImportError:
            return "Error: python-docx library not available for reading DOCX files"
        except Exception as e:
            return f"Error reading DOCX file {file_name}: {e}"

    def read_text_file(self, file_name: str) -> str:
        """
        Reads a text file and extracts content.
        
        Args:
            file_name: Name of the text file to read
            
        Returns:
            str: Extracted content from text file
        """
        # Get file path (download from GCP if necessary)
        target_file = self._get_file_path(file_name)
        
        if not target_file:
            return f"Text file '{file_name}' not found in available files."
        
        try:
            # Try different encodings
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    with open(target_file, 'r', encoding=encoding) as f:
                        content = f.read()
                        if content.strip():
                            return content
                except UnicodeDecodeError:
                    continue
            
            return "No readable text content found in file"
        except Exception as e:
            return f"Error reading text file {file_name}: {e}"

    def _read_document_content(self, file_path: Path) -> str:
        """Read document content based on file extension."""
        file_extension = file_path.suffix.lower()
        
        if file_extension == '.pdf':
            return self.read_pdf_file(file_path.name)
        elif file_extension in ['.xlsx', '.xls']:
            return self.read_excel_file(file_path.name)
        elif file_extension == '.csv':
            return self.read_csv_file(file_path.name)
        elif file_extension == '.docx':
            return self.read_docx_file(file_path.name)
        elif file_extension in ['.txt', '.md', '.json', '.xml', '.html', '.htm']:
            return self.read_text_file(file_path.name)
        else:
            return f"Unsupported file format: {file_extension}. Supported formats: PDF, Excel, CSV, DOCX, TXT, MD, JSON, XML, HTML"

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
        """Split text into chunks with overlap."""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
            if start >= len(text):
                break
        
        return chunks

    def __del__(self):
        """Cleanup temporary files when toolkit is destroyed."""
        for temp_file in self.temp_files:
            try:
                Path(temp_file).unlink(missing_ok=True)
            except Exception:
                pass


# Legacy function for backward compatibility
@tool(show_result=False)
def DirectDocumentReaderTool(**kwargs: Any) -> str:
    """
    Legacy function for reading uploaded files in various formats.
    Consider using DocumentReaderTools toolkit instead.
    """
    files: Optional[List[Path]] = kwargs.get("files")
    query: Optional[str] = kwargs.get("query")

    if not files:
        return "No files were uploaded."
    if not query:
        return "No question was provided."

    # Create a temporary toolkit instance
    toolkit = DocumentReaderTools(files=list(files))
    
    # Read all documents
    all_content = []
    for file_path in files:
        content = toolkit._read_document_content(file_path)
        if not content.startswith("Error:"):
            all_content.append(content)
        else:
            return content

    if not all_content:
        return "No documents could be loaded from the uploaded files."

    # Combine and chunk content
    combined_content = "\n\n---\n\n".join(all_content)
    chunks = toolkit._chunk_text(combined_content, chunk_size=512, overlap=50)
    context = "\n\n---\n\n".join(chunks)[:12000]  # trim if too long

    # Generate prompt
    prompt = f"""Here is the content extracted from the uploaded documents:

{context}

Based on the documents above, please answer the following question clearly and concisely:

{query}
"""
    return prompt

