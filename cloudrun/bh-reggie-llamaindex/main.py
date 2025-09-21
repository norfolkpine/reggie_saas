import logging
import os
import urllib.parse
import tempfile
import asyncio
import time
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Any, List, Dict, Optional
from io import BytesIO
import openai

import httpx

# Text extraction libraries
# Vault processing now uses unified LlamaIndex service for all file types
try:
    import PyPDF2
    from docx import Document as DocxDocument
    from pptx import Presentation
    import openpyxl
    import tiktoken
    PDF_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some text extraction libraries not available: {e}")
    PDF_AVAILABLE = False

# === Ingest a single GCS file ===
from fastapi import FastAPI, HTTPException
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.gcs import GCSReader
from llama_index.vector_stores.postgres import PGVectorStore
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from tqdm import tqdm


# === Load environment variables early ===
def load_env(secret_id="llamaindex-ingester-env", env_file=".env"):
    """
    Load environment variables:
    - If FORCE_LOCAL_ENV=1, load from .env only.
    - If running in GCP, load from Secret Manager.
    - Else, fallback to .env.
    """
    from dotenv import load_dotenv
    from google.auth.exceptions import DefaultCredentialsError

    # === FORCE LOCAL OVERRIDE ===
    if os.getenv("FORCE_LOCAL_ENV") == "1":
        if load_dotenv(env_file):
            print(f"✅ Forced local: Loaded environment from {env_file}")
        else:
            print(f"⚠️ Forced local: Failed to load {env_file}")
        return

    def is_gcp_environment():
        try:
            import requests

            response = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/",
                headers={"Metadata-Flavor": "Google"},
                timeout=1.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    if is_gcp_environment():
        # Try to load from Secret Manager
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not project_id:
                raise ValueError("GCP_PROJECT or GOOGLE_CLOUD_PROJECT env var not set")
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            env_content = response.payload.data.decode("UTF-8")
            for line in env_content.splitlines():
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value
            print(f"✅ Loaded environment from Secret Manager: {secret_id}")
            return
        except (Exception, DefaultCredentialsError) as e:
            print(f"⚠️ Failed to load from Secret Manager: {e} — falling back to .env")

    # === DEVELOPMENT ===
    if load_dotenv(env_file):
        print(f"✅ Loaded environment from {env_file}")
    else:
        print(f"⚠️ Failed to load {env_file}")


# Call load_env before any config variable reads
load_env()

# === Config Variables ===
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "bh-reggie-media")

# Validate required environment variables
if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable is required")

POSTGRES_URL = os.getenv("POSTGRES_URL")
VECTOR_TABLE_NAME = os.getenv("PGVECTOR_TABLE")
SCHEMA_NAME = os.getenv("PGVECTOR_SCHEMA", "ai")  # Changed default to "ai"
# Unified Vault vector table configuration
VAULT_VECTOR_TABLE = os.getenv("VAULT_PGVECTOR_TABLE", "vault_embeddings")  # Single unified table for all Vault files
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Added for Gemini
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")  # Default, might be provider specific
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))  # TODO: This might need to be dynamic
DJANGO_API_URL = os.getenv("DJANGO_API_URL", "http://localhost:8000")
DJANGO_API_KEY = os.getenv("DJANGO_API_KEY")  # System API key for Cloud Run

# Validate Django API key - required for progress updates
if not DJANGO_API_KEY:
    raise ValueError("DJANGO_API_KEY environment variable is required for progress updates")

# === Logging Setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("llama_index")
logger.setLevel(logging.INFO)


# Create settings object for progress updates
class Settings:
    DJANGO_API_URL = DJANGO_API_URL
    DJANGO_API_KEY = DJANGO_API_KEY
    API_PREFIX = "reggie/api/v1"  # Include reggie prefix for correct URL routing

    @property
    def auth_headers(self):
        """Return properly formatted auth headers for system API key."""
        if not self.DJANGO_API_KEY:
            logger.error("❌ No API key configured - progress updates will fail!")
            raise HTTPException(
                status_code=500,
                detail="Django API key is required for progress updates. Ingestion will continue but progress won't be tracked.",
            ) from None

        # Log the header being used (with masked key)
        masked_key = f"{self.DJANGO_API_KEY[:4]}...{self.DJANGO_API_KEY[-4:]}"
        logger.info(f"🔑 Using System API Key: {masked_key}")

        return {
            "Authorization": f"Api-Key {self.DJANGO_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Request-Source": "cloud-run-ingestion",
        }

    def update_file_progress_sync(
        self,
        file_uuid: str,
        progress: float,
        processed_docs: int,
        total_docs: int,
        link_id: int | None = None,
        error: str | None = None,
    ):
        """Update file ingestion progress."""
        try:
            with httpx.Client() as client:
                # Remove trailing slash from base URL and ensure API_PREFIX doesn't start with slash
                base_url = self.DJANGO_API_URL.rstrip("/")
                api_prefix = self.API_PREFIX.lstrip("/")
                url = f"{base_url}/{api_prefix}/files/{file_uuid}/update-progress/"

                # Ensure progress is between 0 and 100
                progress = min(max(progress, 0), 100)

                data = {
                    "progress": round(progress, 2),  # Round to 2 decimal places
                    "processed_docs": processed_docs,
                    "total_docs": total_docs,
                }

                # Only include link_id if it's provided and valid
                if link_id is not None and link_id > 0:
                    data["link_id"] = link_id

                if error:
                    data["error"] = error

                response = client.post(url, headers=self.auth_headers, json=data, timeout=10.0)
                self.validate_auth_response(response)

                # Log different messages based on progress
                if progress >= 100:
                    logger.info(f"✅ Ingestion completed: {processed_docs}/{total_docs} documents")
                else:
                    logger.info(f"📊 Progress updated: {progress:.1f}% ({processed_docs}/{total_docs})")

                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Failed to update progress: {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to update progress: {str(e)}")
            raise

    def validate_auth_response(self, response):
        """Validate authentication response and log helpful messages."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.error("❌ Authentication failed - invalid or revoked API key")
                logger.error(f"Response body: {e.response.text}")
                # Re-raise with more helpful message
                raise HTTPException(
                    status_code=403,
                    detail="Authentication failed. Please ensure your system API key is valid and not revoked.",
                )
            raise


settings = Settings()


@lru_cache(maxsize=1)
def get_vector_store(vector_table_name, current_embed_dim):
    # Async engine
    async_engine = create_async_engine(
        POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )
    engine = create_engine(
        POSTGRES_URL,
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )

    return PGVectorStore(
        engine=engine,
        async_engine=async_engine,
        table_name=vector_table_name,
        embed_dim=current_embed_dim,
        schema_name=SCHEMA_NAME,
        perform_setup=True,
    )


# === Utility Functions ===

def download_gcs_file(file_path: str) -> bytes:
    """Download file from Google Cloud Storage"""
    try:
        from google.cloud import storage
        
        # Parse GCS path
        if file_path.startswith("gs://"):
            path_parts = file_path[5:].split("/", 1)
            bucket_name = path_parts[0]
            blob_name = path_parts[1] if len(path_parts) > 1 else ""
        else:
            bucket_name = GCS_BUCKET_NAME
            blob_name = file_path
        
        # Download file
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        return blob.download_as_bytes()
        
    except Exception as e:
        logger.error(f"Failed to download file from GCS: {e}")
        raise


def extract_text_from_pdf_langextract(file_content: bytes) -> tuple[str, dict]:
    """Enhanced PDF extraction using LangExtract and Unstructured"""
    try:
        # LangExtract removed - all vault processing uses unified LlamaIndex service
        if True:  # Always use fallback since LangExtract is removed
            return extract_text_from_pdf_fallback(file_content), {}
            
        # Try LangExtract first for intelligent extraction
        try:
            # Save content to temporary file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()
                
                # Use LangExtract for intelligent extraction
                result = langextract_extract(tmp_file.name)
                
                # Clean up temp file
                os.unlink(tmp_file.name)
                
                if result and hasattr(result, 'text') and result.text:
                    text_content = result.text
                    metadata = {
                        "extraction_method": "langextract_primary",
                        "document_structure": getattr(result, 'structure', []),
                        "entities": getattr(result, 'entities', {}),
                        "tables": getattr(result, 'tables', []),
                        "metadata": getattr(result, 'metadata', {}),
                        "langextract_version": getattr(langextract, '__version__', 'unknown')
                    }
                    logger.info(f"✅ LangExtract Primary: Extracted {len(text_content)} chars")
                    return text_content, metadata
                elif result:
                    # Try different attributes that might contain the text
                    text_content = str(result)
                    metadata = {
                        "extraction_method": "langextract_primary",
                        "langextract_result": str(type(result)),
                        "langextract_version": getattr(langextract, '__version__', 'unknown')
                    }
                    logger.info(f"✅ LangExtract Primary (fallback): Extracted {len(text_content)} chars")
                    return text_content, metadata
                    
        except Exception as le_error:
            logger.warning(f"⚠️ LangExtract primary extraction failed: {le_error}, trying unstructured...")
            
        # Fallback to unstructured processing  
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_file.flush()
            
            # Use unstructured to partition PDF with enhanced extraction
            elements = partition_pdf(
                filename=tmp_file.name,
                strategy="hi_res",  # High-resolution strategy for better text extraction
                infer_table_structure=True,  # Extract table structure
                extract_images_in_pdf=False,  # Skip images for now
                include_page_breaks=True
            )
            
            # Clean up temp file
            os.unlink(tmp_file.name)
            
        # Extract structured content with metadata
        text_content = []
        metadata = {
            "extraction_method": "unstructured_fallback",
            "document_structure": [],
            "tables": [],
            "sections": []
        }
        
        for element in elements:
            text = element.text.strip()
            if text:
                element_type = str(type(element).__name__)
                text_content.append(f"[{element_type}] {text}")
                
                # Capture structural information
                if hasattr(element, 'metadata'):
                    meta = element.metadata
                    if element_type == "Table":
                        metadata["tables"].append({
                            "text": text,
                            "page": getattr(meta, 'page_number', 0)
                        })
                    elif element_type in ["Title", "Header"]:
                        metadata["sections"].append({
                            "title": text,
                            "type": element_type,
                            "page": getattr(meta, 'page_number', 0)
                        })
                        
                metadata["document_structure"].append({
                    "type": element_type,
                    "text": text[:100] + "..." if len(text) > 100 else text,
                    "length": len(text)
                })
        
        final_text = "\n\n".join(text_content)
        logger.info(f"✅ Unstructured PDF: Extracted {len(final_text)} chars with {len(elements)} elements")
        return final_text, metadata
        
    except Exception as e:
        logger.error(f"❌ LangExtract PDF failed, falling back to basic extraction: {e}")
        return extract_text_from_pdf_fallback(file_content), {}


def extract_text_from_docx_langextract(file_content: bytes) -> tuple[str, dict]:
    """Enhanced DOCX extraction using LangExtract/Unstructured"""
    try:
        # LangExtract removed - all vault processing uses unified LlamaIndex service
        if True:  # Always use fallback since LangExtract is removed
            return extract_text_from_docx_fallback(file_content), {}
            
        # Save content to temporary file
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_file.flush()
            
            # Use unstructured to partition DOCX
            elements = partition_docx(
                filename=tmp_file.name,
                infer_table_structure=True
            )
            
            # Clean up temp file
            os.unlink(tmp_file.name)
            
        # Extract structured content
        text_content = []
        metadata = {
            "document_structure": [],
            "tables": [],
            "headers": []
        }
        
        for element in elements:
            text = element.text.strip()
            if text:
                element_type = str(type(element).__name__)
                text_content.append(f"[{element_type}] {text}")
                
                if element_type == "Table":
                    metadata["tables"].append({"text": text})
                elif element_type in ["Title", "Header"]:
                    metadata["headers"].append({"text": text, "type": element_type})
                    
                metadata["document_structure"].append({
                    "type": element_type,
                    "text": text[:100] + "..." if len(text) > 100 else text
                })
        
        final_text = "\n\n".join(text_content)
        logger.info(f"✅ LangExtract DOCX: Extracted {len(final_text)} chars with {len(elements)} elements")
        return final_text, metadata
        
    except Exception as e:
        logger.error(f"❌ LangExtract DOCX failed, falling back: {e}")
        return extract_text_from_docx_fallback(file_content), {}


def extract_text_from_pptx_langextract(file_content: bytes) -> tuple[str, dict]:
    """Enhanced PPTX extraction using LangExtract/Unstructured"""
    try:
        # LangExtract removed - all vault processing uses unified LlamaIndex service
        if True:  # Always use fallback since LangExtract is removed
            return extract_text_from_pptx_fallback(file_content), {}
            
        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_file.flush()
            
            elements = partition_pptx(filename=tmp_file.name)
            os.unlink(tmp_file.name)
            
        text_content = []
        metadata = {
            "slides": [],
            "document_structure": []
        }
        
        current_slide = 1
        for element in elements:
            text = element.text.strip()
            if text:
                element_type = str(type(element).__name__)
                text_content.append(f"[Slide {current_slide} - {element_type}] {text}")
                
                metadata["slides"].append({
                    "slide_number": current_slide,
                    "type": element_type,
                    "text": text
                })
                
                if "PageBreak" in element_type:
                    current_slide += 1
        
        final_text = "\n\n".join(text_content)
        logger.info(f"✅ LangExtract PPTX: Extracted {len(final_text)} chars from {current_slide} slides")
        return final_text, metadata
        
    except Exception as e:
        logger.error(f"❌ LangExtract PPTX failed, falling back: {e}")
        return extract_text_from_pptx_fallback(file_content), {}


def extract_text_from_excel_langextract(file_content: bytes) -> tuple[str, dict]:
    """Enhanced Excel extraction using LangExtract/Unstructured"""
    try:
        # LangExtract removed - all vault processing uses unified LlamaIndex service
        if True:  # Always use fallback since LangExtract is removed
            return extract_text_from_excel_fallback(file_content), {}
            
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_file.flush()
            
            elements = partition_xlsx(filename=tmp_file.name)
            os.unlink(tmp_file.name)
            
        text_content = []
        metadata = {
            "sheets": [],
            "tables": []
        }
        
        for element in elements:
            text = element.text.strip()
            if text:
                element_type = str(type(element).__name__)
                text_content.append(f"[{element_type}] {text}")
                
                if element_type == "Table":
                    metadata["tables"].append({"content": text})
                
                metadata["sheets"].append({
                    "type": element_type,
                    "text": text
                })
        
        final_text = "\n\n".join(text_content)
        logger.info(f"✅ LangExtract Excel: Extracted {len(final_text)} chars")
        return final_text, metadata
        
    except Exception as e:
        logger.error(f"❌ LangExtract Excel failed, falling back: {e}")
        return extract_text_from_excel_fallback(file_content), {}


# Fallback functions (original implementations)
def extract_text_from_pdf_fallback(file_content: bytes) -> str:
    """Fallback PDF extraction using PyPDF2"""
    try:
        pdf_file = BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        raise


def extract_text_from_docx_fallback(file_content: bytes) -> str:
    """Fallback DOCX extraction using python-docx"""
    try:
        docx_file = BytesIO(file_content)
        doc = DocxDocument(docx_file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from DOCX: {e}")
        raise


def extract_text_from_pptx_fallback(file_content: bytes) -> str:
    """Fallback PPTX extraction using python-pptx"""
    try:
        pptx_file = BytesIO(file_content)
        prs = Presentation(pptx_file)
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from PPTX: {e}")
        raise


def extract_text_from_excel_fallback(file_content: bytes) -> str:
    """Fallback Excel extraction using openpyxl"""
    try:
        excel_file = BytesIO(file_content)
        workbook = openpyxl.load_workbook(excel_file)
        text = ""
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            text += f"Sheet: {sheet_name}\n"
            for row in sheet.iter_rows(values_only=True):
                row_text = [str(cell) if cell is not None else "" for cell in row]
                text += "\t".join(row_text) + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from Excel: {e}")
        raise


async def generate_embeddings(text_chunks: list) -> dict:
    """Generate embeddings for text chunks using OpenAI"""
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        embeddings = []
        total_tokens = 0
        
        for chunk in text_chunks:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=chunk
            )
            embeddings.append(response.data[0].embedding)
            total_tokens += response.usage.total_tokens
        
        return {
            "embeddings": embeddings,
            "tokens_used": total_tokens
        }
        
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise


async def store_vault_embeddings_enhanced(project_uuid: str, user_uuid: str, file_id: int, text_chunks: list, embeddings: list, base_metadata: dict, chunk_metadata_list: list):
    """DEPRECATED: Legacy Agno storage function - now using LlamaIndex native approach"""
    logger.warning("🚨 Deprecated function store_vault_embeddings_enhanced called - this should use LlamaIndex native storage instead")
    logger.warning("⚠️ Vault embeddings should now be processed through process_vault_file_without_progress function")
    raise NotImplementedError(
        "Legacy Agno storage methods are deprecated. Use process_vault_file_without_progress() "
        "which handles embedding through LlamaIndex native PGVectorStore for proper schema compatibility."
    )


async def store_vault_embeddings(project_uuid: str, user_uuid: str, file_id: int, text_chunks: list, embeddings: list, metadata: dict):
    """DEPRECATED: Legacy Agno storage function - now using LlamaIndex native approach"""
    logger.warning("🚨 Deprecated function store_vault_embeddings called - this should use LlamaIndex native storage instead")
    logger.warning("⚠️ Vault embeddings should now be processed through process_vault_file_without_progress function")
    raise NotImplementedError(
        "Legacy Agno storage methods are deprecated. Use process_vault_file_without_progress() "
        "which handles embedding through LlamaIndex native PGVectorStore for proper schema compatibility."
    )

async def ensure_vault_vector_table_exists():
    """Ensure unified Vault vector table exists with LlamaIndex-compatible schema"""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(POSTGRES_URL)

        with engine.connect() as conn:
            # Create schema if it doesn't exist
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))

            # Let LlamaIndex PGVectorStore handle table creation with correct schema
            conn.commit()
            logger.info(f"✅ Schema {SCHEMA_NAME} ready for LlamaIndex vault table creation")

    except Exception as e:
        logger.error(f"Failed to ensure Vault vector table exists: {e}")
        raise


# === FastAPI App ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI app."""
    # Load environment variables
    # load_env(secret_id="llamaindex-ingester-env")
    # load_env()

    # Validate required environment variables for Django communication
    if not DJANGO_API_KEY:
        logger.warning("⚠️ No API key configured - progress updates to Django will fail!")
    else:
        logger.info(f"✅ Django API key configured for {DJANGO_API_URL}")
        # Skip health check during startup to avoid hanging
        # The health check can be done during actual API calls if needed

    yield

    # Cleanup (if needed)
    logger.info("Shutting down...")


app = FastAPI(lifespan=lifespan)


# === Request Models ===
class IngestRequest(BaseModel):
    gcs_prefix: str
    file_limit: int | None = None
    vector_table_name: str


class FileIngestRequest(BaseModel):
    file_path: str = Field(..., description="Full GCS path to the file")
    vector_table_name: str = Field(..., description="Name of the vector table to store embeddings")
    file_uuid: str = Field(..., description="UUID of the file in Django")
    link_id: int | None = Field(None, description="Optional link ID for tracking specific ingestion")
    embedding_provider: str = Field(..., description="Embedding provider, e.g., 'openai' or 'google'")
    embedding_model: str = Field(
        ..., description="Model to use for embeddings, e.g., 'text-embedding-ada-002' or 'models/embedding-004'"
    )
    chunk_size: int | None = Field(1000, description="Size of text chunks")
    chunk_overlap: int | None = Field(200, description="Overlap between chunks")
    batch_size: int | None = Field(20, description="Number of documents to process in each batch")
    progress_update_frequency: int | None = Field(10, description="Minimum percentage points between progress updates")

    # ===== NEW METADATA FIELDS =====
    # Required metadata fields
    user_uuid: str = Field(..., description="UUID of the user who owns this document")
    team_id: str | None = Field(None, description="ID of the team this document belongs to")

    # Conditional metadata fields
    knowledgebase_id: str | None = Field(None, description="ID of the knowledge base (conditional)")
    project_id: str | None = Field(None, description="ID of the project (conditional)")

    # Additional optional metadata
    custom_metadata: dict[str, Any] | None = Field(None, description="Additional custom metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "gs://your-bucket/path/to/file.pdf",
                "vector_table_name": "your_vector_table",
                "file_uuid": "123e4567-e89b-12d3-a456-426614174000",
                "link_id": 1,
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-ada-002",
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "batch_size": 20,
                "progress_update_frequency": 10,
                # New metadata fields
                "user_uuid": "user_123e4567-e89b-12d3-a456-426614174000",
                # "team_id": "team_987fcdeb-51a2-43d1-9c4e-567890123456",  # Example: optional field
                "knowledgebase_id": "kb_456789ab-cdef-1234-5678-90abcdef1234",
                "project_id": "proj_789abcde-f123-4567-890a-bcdef1234567",
                "custom_metadata": {"department": "engineering", "priority": "high"},
            }
        }

    def clean_file_path(self) -> str:
        """Clean and validate the file path."""
        path = self.file_path

        # Log original path
        logger.info(f"🔍 Original file path: {path}")

        # Handle gs:// prefix
        if path.startswith("gs://"):
            # Split into bucket and path parts
            parts = path[5:].split("/", 1)
            if len(parts) == 2:
                bucket_name, file_path = parts
                # Don't modify the path structure, just ensure no double slashes
                path = f"gs://{bucket_name}/{file_path}"
        else:
            # If no gs:// prefix, add it with the configured bucket
            path = f"gs://{GCS_BUCKET_NAME}/{path}"

        # Log path after gs:// handling
        logger.info(f"🔍 Path after gs:// handling: {path}")

        # Extract bucket and path
        if path.startswith("gs://"):
            parts = path[5:].split("/", 1)
            if len(parts) > 1:
                bucket_name, file_path = parts
                logger.info(f"🔍 Using bucket: {bucket_name}")
                logger.info(f"🔍 Using file path: {file_path}")

        # Remove any double slashes (but preserve gs://)
        if "gs://" in path:
            gs_parts = path.split("gs://", 1)
            path = "gs://" + gs_parts[1].replace("//", "/")
        else:
            path = path.replace("//", "/")

        logger.info(f"🔍 Final cleaned path: {path}")
        return path


class DeleteVectorRequest(BaseModel):
    vector_table_name: str = Field(..., description="Name of the vector table containing the vectors")
    file_uuid: str = Field(..., description="UUID of the file whose vectors should be deleted")


# === Common indexing logic ===
def index_documents(docs, source: str, vector_table_name: str, embed_model):  # Modified to accept embed_model
    if not docs:
        raise HTTPException(status_code=404, detail=f"No documents found for {source}")

    logger.info(
        f"📊 Starting embedding for {len(docs)} documents from source: {source} using {embed_model.__class__.__name__}"
    )
    # embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY) # Removed: embed_model is now passed

    vector_store = PGVectorStore(
        connection_string=POSTGRES_URL,
        async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
        table_name=vector_table_name,
        embed_dim=EMBED_DIM,
        schema_name=SCHEMA_NAME,
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info("🧠 Building VectorStoreIndex...")
    VectorStoreIndex.from_documents(
        docs, storage_context=storage_context, embed_model=embed_model
    )  # Use passed embed_model
    logger.info("✅ Embedding and indexing complete.")

    return {"indexed_documents": len(docs), "source": source, "vector_table": vector_table_name}


# === Ingest by GCS prefix (bulk mode) ===
@app.post("/ingest-gcs")
async def ingest_gcs_docs(payload: IngestRequest):
    try:
        logger.info(f"🔎 Starting GCS ingestion for prefix: {payload.gcs_prefix}")
        reader_kwargs = {"bucket": GCS_BUCKET_NAME, "prefix": payload.gcs_prefix}

        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH

        reader = GCSReader(**reader_kwargs)

        resources = reader.list_resources()
        if payload.file_limit:
            resources = resources[: payload.file_limit]
        logger.info(f"📦 Found {len(resources)} resources")

        documents = []
        for name in tqdm(resources, desc="📂 Loading docs"):
            logger.info(f"📄 Loading file: {name}")
            try:
                result = reader.load_resource(name)
                loaded_docs = result if isinstance(result, list) else [result]
                # consider adding custom metadata doc.metadata {}
                documents.extend(loaded_docs)
            except Exception as e:
                logger.warning(f"❌ Failed to load {name}: {str(e)}")

        # For now, /ingest-gcs will default to OpenAI as it doesn't have provider selection yet
        # TODO: Future improvement: Allow provider selection for /ingest-gcs
        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY is not set. Cannot proceed with default GCS ingestion.")
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set for GCS ingestion.")

        default_embedder = OpenAIEmbedding(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
        logger.info(f"⚠️ /ingest-gcs defaulting to OpenAI embeddings ({EMBEDDING_MODEL}).")
        return index_documents(
            documents,
            source=payload.gcs_prefix,
            vector_table_name=payload.vector_table_name,
            embed_model=default_embedder,
        )

    except Exception as e:
        import traceback

        logger.error(f"❌ Ingestion error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/ingest-file")
def ingest_single_file(payload: FileIngestRequest):
    logger.info(f"📄 Queuing ingestion for file: {payload.file_path}")
    process_single_file(payload)
    return {"status": "queued", "file_path": payload.file_path}


def process_single_file(payload: FileIngestRequest):
    try:
        logger.info(f"📄 Ingesting single file: {payload.file_path}")

        # Step 1: Clean and validate file path
        file_path = payload.clean_file_path()

        if not GCS_BUCKET_NAME:
            raise ValueError("GCS_BUCKET_NAME is not configured")

        logger.info(f"🔍 Using cleaned path: {file_path}")
        logger.info(f"🔍 Using GCS bucket: {GCS_BUCKET_NAME}")

        # Extract the actual file path from the GCS URL
        if file_path.startswith("gs://"):
            parts = file_path[5:].split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid GCS path format: {file_path}")
            bucket_name, actual_path = parts
            if bucket_name != GCS_BUCKET_NAME:
                raise ValueError(f"File is in bucket {bucket_name} but service is configured for {GCS_BUCKET_NAME}")
            file_path = actual_path

        # Step 2: Reading file with GCS Reader
        reader_kwargs = {
            "bucket": GCS_BUCKET_NAME,
            "key": file_path,
        }

        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH
            logger.info(f"📚 Using credentials from: {CREDENTIALS_PATH}")

        logger.info(f"📚 Initializing GCS reader with bucket: {GCS_BUCKET_NAME}, key: {file_path}")
        reader = GCSReader(**reader_kwargs)

        try:
            # Try to load the data
            logger.info(f"📚 Attempting to load file from bucket: {GCS_BUCKET_NAME}")
            logger.info(f"📚 Using file path: {file_path}")
            result = reader.load_data()

            if not result:
                # If that fails, try with URL-decoded path
                decoded_path = urllib.parse.unquote(file_path)
                if decoded_path != file_path:
                    logger.info(f"📚 First attempt failed. Retrying with decoded path: {decoded_path}")
                    reader_kwargs["key"] = decoded_path
                    reader = GCSReader(**reader_kwargs)
                    result = reader.load_data()

            if not result:
                error_msg = f"No content loaded from file after multiple attempts. Path tried: {file_path}"
                if "decoded_path" in locals():
                    error_msg += f", {decoded_path}"
                logger.error(error_msg)
                raise ValueError(error_msg)

        except Exception as e:
            error_msg = f"❌ Failed to read file {file_path} from bucket {GCS_BUCKET_NAME}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Reader kwargs: {reader_kwargs}")
            logger.error(f"Original file path: {payload.file_path}")
            logger.error(f"Cleaned file path: {file_path}")

            # Update progress to failed state if we have link_id
            if payload.link_id:
                try:
                    settings.update_file_progress_sync(
                        file_uuid=payload.file_uuid,
                        progress=0,
                        processed_docs=0,
                        total_docs=0,
                        link_id=payload.link_id,
                        error=error_msg,
                    )
                except Exception as progress_e:
                    logger.error(f"Failed to update progress after file read error: {progress_e}")
            raise HTTPException(status_code=500, detail=error_msg)

        documents = result if isinstance(result, list) else [result]
        total_docs = len(documents)
        if total_docs == 0:
            raise HTTPException(status_code=400, detail=f"No documents extracted from file: {file_path}")

        logger.info(f"📄 Processing {total_docs} documents from file")
        processed_docs = 0

        # Send initial progress update
        settings.update_file_progress_sync(
            file_uuid=payload.file_uuid, progress=0, processed_docs=0, total_docs=total_docs, link_id=payload.link_id
        )

        # === Dynamic Embedder Instantiation ===
        embedder = None
        current_embed_dim = EMBED_DIM  # Default, will try to update based on model
        logger.info(f"Requested embedding provider: {payload.embedding_provider}, model: {payload.embedding_model}")

        if payload.embedding_provider == "openai":
            if not OPENAI_API_KEY:
                raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
            embedder = OpenAIEmbedding(model=payload.embedding_model, api_key=OPENAI_API_KEY)
            if hasattr(embedder, "dimensions") and embedder.dimensions:
                current_embed_dim = embedder.dimensions
            else:
                logger.warning(
                    f"Could not determine dimensions for OpenAI model {payload.embedding_model}. Falling back to default EMBED_DIM={EMBED_DIM}."
                )
        elif payload.embedding_provider == "google":
            if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                logger.warning(
                    "Neither GOOGLE_API_KEY nor GOOGLE_APPLICATION_CREDENTIALS is set. Gemini Embedding might fail."
                )

            try:
                embedder = GeminiEmbedding(model_name=payload.embedding_model)
                # Attempt to get dimensions. This is a bit of a guess for Gemini.
                # LlamaIndex's GeminiEmbedding might not have a direct 'dimensions' attribute.
                # We might need a mapping for known models.
                # Example: "models/embedding-004" is 768.
                # model_name for GeminiEmbedding is like "models/embedding-001"
                if (
                    "embedding-004" in payload.embedding_model or "embedding-001" in payload.embedding_model
                ):  # Newer model
                    current_embed_dim = 768
                # Add more known models here or find a programmatic way if available
                else:
                    # If model is unknown, try to get from a 'dimensions' attribute if it exists (speculative)
                    if hasattr(embedder, "dimensions") and embedder.dimensions:
                        current_embed_dim = embedder.dimensions
                    else:
                        logger.warning(
                            f"Cannot determine dimension for Google model {payload.embedding_model}. Using default {EMBED_DIM}. This might be incorrect."
                        )

            except Exception as e:
                logger.error(f"Failed to initialize GeminiEmbedding: {str(e)}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to initialize Google Gemini Embedding: {str(e)}"
                ) from e
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported embedding provider: {payload.embedding_provider}")

        if embedder is None:
            raise HTTPException(status_code=500, detail="Failed to initialize embedder.")

        logger.info(f"✅ Initialized embedder: {embedder.__class__.__name__} with model {payload.embedding_model}")
        logger.info(f"✅ Using embedding dimension: {current_embed_dim} for vector store.")

        print("payload.vector_table_name", payload.vector_table_name)

        # Create vector store with tested dimension
        vector_store = get_vector_store(payload.vector_table_name, current_embed_dim)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # SIMPLIFIED METADATA (just the essentials)
        base_metadata = {
            "file_uuid": payload.file_uuid,
            "user_uuid": payload.user_uuid,
            "ingested_at": datetime.now().isoformat(),
        }

        # Add optional fields if they exist
        if payload.team_id:
            base_metadata["team_id"] = payload.team_id
            base_metadata["access_level"] = "team"  # Mark as team-accessible
        else:
            base_metadata["access_level"] = "user"  # Mark as user-only
            
        if payload.knowledgebase_id:
            base_metadata["knowledgebase_id"] = payload.knowledgebase_id
        if payload.project_id:
            base_metadata["project_id"] = payload.project_id
        if payload.link_id:
            base_metadata["link_id"] = str(payload.link_id)
        
        # Add any custom metadata if provided
        if payload.custom_metadata:
            for key, value in payload.custom_metadata.items():
                if key not in base_metadata:  # Don't override core metadata
                    base_metadata[key] = value

        # Process documents with your working pattern
        text_splitter = TokenTextSplitter(chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap)
        batch_size = payload.batch_size
        processed_docs = 0

        try:
            for i in range(0, total_docs, batch_size):
                batch = documents[i : i + batch_size]
                chunked_docs = []

                for doc in batch:
                    # Ensure document has content
                    if not doc.text or not doc.text.strip():
                        continue

                    text_chunks = text_splitter.split_text(doc.text)

                    # Combine your base metadata with any existing doc metadata
                    doc_metadata = base_metadata.copy()
                    if doc.metadata:
                        # Add original metadata but keep base_metadata as priority
                        for key, value in doc.metadata.items():
                            if key not in doc_metadata:  # Don't override base metadata
                                doc_metadata[key] = value

                    # YOUR WORKING PATTERN: Simple list comprehension
                    batch_chunks = [
                        Document(text=chunk, metadata=doc_metadata) for chunk in text_chunks if chunk.strip()
                    ]

                    chunked_docs.extend(batch_chunks)

                # Debug batch info
                logger.info(f"📋 Batch {i // batch_size + 1}: {len(chunked_docs)} chunks")

                if chunked_docs:  # Only process if we have chunks
                    # Index the chunked documents
                    VectorStoreIndex.from_documents(chunked_docs, storage_context=storage_context, embed_model=embedder)

                    processed_docs += len(batch)
                    progress = (processed_docs / total_docs) * 100

                    # Update progress
                    settings.update_file_progress_sync(
                        file_uuid=payload.file_uuid,
                        progress=progress,
                        processed_docs=processed_docs,
                        total_docs=total_docs,
                        link_id=payload.link_id,
                    )

                    logger.info(f"✅ Batch {i // batch_size + 1} completed. Progress: {progress:.1f}%")
                else:
                    logger.warning(f"⚠️ Batch {i // batch_size + 1} had no valid chunks")
                    if payload.link_id:
                        try:
                            settings.update_file_progress_sync(
                                file_uuid=payload.file_uuid,
                                progress=progress,  # Keep the last progress
                                processed_docs=processed_docs,
                                total_docs=total_docs,
                                link_id=payload.link_id,
                            )
                        except Exception as progress_e:
                            logger.error(f"Failed to update progress after batch error: {progress_e}")
                    raise HTTPException(
                        status_code=500, detail="Failed to process documents: batch had no valid chunks"
                    ) from None

            # Final progress update
            settings.update_file_progress_sync(
                file_uuid=payload.file_uuid,
                progress=100,
                processed_docs=total_docs,
                total_docs=total_docs,
                link_id=payload.link_id,
            )

            logger.info(f"✅ Successfully processed {total_docs} documents")
            return {
                "status": "completed",
                "message": f"Successfully processed {total_docs} documents",
                "total_docs": total_docs,
                "file_path": file_path,
                "embedding_dimension": current_embed_dim,
            }

        except Exception as e:
            logger.error(f"❌ Error during batch processing: {str(e)}")
            if payload.link_id:
                try:
                    settings.update_file_progress_sync(
                        file_uuid=payload.file_uuid,
                        progress=progress if "progress" in locals() else 0,
                        processed_docs=processed_docs,
                        total_docs=total_docs,
                        link_id=payload.link_id,
                    )
                except Exception as progress_e:
                    logger.error(f"Failed to update progress after processing error: {progress_e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error ingesting file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# === Delete vectors for a file ===
@app.post("/delete-vectors")
async def delete_vectors(payload: DeleteVectorRequest):
    try:
        logger.info(f"🗑️ Deleting vectors for file: {payload.file_uuid}")

        # Initialize vector store
        vector_store = PGVectorStore(
            connection_string=POSTGRES_URL,
            async_connection_string=POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
            table_name=payload.vector_table_name,
            embed_dim=EMBED_DIM,
            schema_name=SCHEMA_NAME,
        )

        # Delete vectors with matching file_uuid in metadata
        deleted_count = vector_store.delete(filter_dict={"file_uuid": payload.file_uuid})

        logger.info(f"✅ Successfully deleted {deleted_count} vectors")
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "file_uuid": payload.file_uuid,
            "vector_table": payload.vector_table_name,
        }

    except Exception as e:
        logger.error(f"❌ Error deleting vectors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/migrate-vault-vectors")
async def migrate_vault_vectors():
    """Migrate vault vectors from old schema to new LlamaIndex-compatible schema"""
    try:
        logger.info("🔄 Starting vault vector schema migration")

        from sqlalchemy import create_engine, text

        engine = create_engine(POSTGRES_URL)
        with engine.connect() as conn:
            # First, backup old table if it exists
            backup_sql = text(f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{VAULT_VECTOR_TABLE}_backup AS
                SELECT * FROM {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} WHERE false;
            """)
            try:
                conn.execute(backup_sql)
            except:
                pass  # Table might not exist yet

            # Drop old table to recreate with new schema
            drop_sql = text(f"DROP TABLE IF EXISTS {SCHEMA_NAME}.{VAULT_VECTOR_TABLE}")
            conn.execute(drop_sql)

            conn.commit()

        # Recreate table with new schema
        await ensure_vault_vector_table_exists()

        logger.info("✅ Successfully migrated vault vector table schema")
        return {
            "success": True,
            "message": "Vault vector table migrated to LlamaIndex-compatible schema"
        }

    except Exception as e:
        logger.error(f"❌ Error migrating vault vectors: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


# === AI Insights endpoints ===

# === Text Extraction Functions ===

async def download_file_from_gcs(bucket_name: str, file_path: str) -> bytes:
    """Download file from Google Cloud Storage"""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        # Download file content
        content = blob.download_as_bytes()
        logger.info(f"✅ Downloaded {len(content)} bytes from gs://{bucket_name}/{file_path}")
        return content
        
    except Exception as e:
        logger.error(f"❌ Failed to download file from GCS: {e}")
        raise

def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF content"""
    try:
        pdf_file = BytesIO(content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
            
        return text.strip()
    except Exception as e:
        logger.error(f"❌ Failed to extract text from PDF: {e}")
        return ""

def extract_text_from_docx(content: bytes) -> str:
    """Extract text from DOCX content"""
    try:
        docx_file = BytesIO(content)
        doc = DocxDocument(docx_file)
        
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
            
        return text.strip()
    except Exception as e:
        logger.error(f"❌ Failed to extract text from DOCX: {e}")
        return ""

def extract_text_from_pptx(content: bytes) -> str:
    """Extract text from PowerPoint content"""
    try:
        pptx_file = BytesIO(content)
        prs = Presentation(pptx_file)
        
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
                    
        return text.strip()
    except Exception as e:
        logger.error(f"❌ Failed to extract text from PPTX: {e}")
        return ""

def extract_text_from_excel(content: bytes) -> str:
    """Extract text from Excel content"""
    try:
        excel_file = BytesIO(content)
        workbook = openpyxl.load_workbook(excel_file)
        
        text = ""
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = " ".join([str(cell) for cell in row if cell is not None])
                if row_text.strip():
                    text += row_text + "\n"
                    
        return text.strip()
    except Exception as e:
        logger.error(f"❌ Failed to extract text from Excel: {e}")
        return ""

def extract_text_from_file_langextract(content: bytes, file_type: str, filename: str) -> tuple[str, dict]:
    """Enhanced text extraction using LangExtract with structure-aware processing"""
    if not PDF_AVAILABLE:
        return f"Text extraction not available - libraries not installed. File: {filename}", {}
    
    file_type = file_type.lower() if file_type else ""
    filename_lower = filename.lower() if filename else ""
    
    try:
        # PDF files - use enhanced LangExtract processing
        if "pdf" in file_type or filename_lower.endswith('.pdf'):
            return extract_text_from_pdf_langextract(content)
        
        # Word documents - use enhanced LangExtract processing
        elif "docx" in file_type or filename_lower.endswith('.docx'):
            return extract_text_from_docx_langextract(content)
            
        # PowerPoint - use enhanced LangExtract processing
        elif "pptx" in file_type or filename_lower.endswith('.pptx'):
            return extract_text_from_pptx_langextract(content)
            
        # Excel files - use enhanced LangExtract processing
        elif "xlsx" in file_type or filename_lower.endswith('.xlsx'):
            return extract_text_from_excel_langextract(content)
            
        # Plain text files
        elif "text" in file_type or filename_lower.endswith(('.txt', '.md', '.csv')):
            text_content = content.decode('utf-8', errors='ignore')
            metadata = {
                "document_structure": [{"type": "PlainText", "text": text_content[:100] + "..." if len(text_content) > 100 else text_content}],
                "file_type": "text"
            }
            return text_content, metadata
            
        else:
            # Try to decode as text for unknown types
            try:
                text_content = content.decode('utf-8', errors='ignore')
                metadata = {
                    "document_structure": [{"type": "Unknown", "text": text_content[:100] + "..." if len(text_content) > 100 else text_content}],
                    "file_type": "unknown",
                    "warning": f"Unknown file type: {file_type}"
                }
                return text_content, metadata
            except:
                return f"Unable to extract text from {filename} (type: {file_type})", {}
                
    except Exception as e:
        logger.error(f"❌ LangExtract text extraction failed for {filename}: {e}")
        return f"Failed to extract text from {filename}: {str(e)}", {}


def extract_text_from_file(content: bytes, file_type: str, filename: str) -> str:
    """Backward compatible text extraction function"""
    text_content, _ = extract_text_from_file_langextract(content, file_type, filename)
    return text_content

def chunk_text_intelligent(elements: list, max_characters: int = 1000) -> List[dict]:
    """Intelligent chunking using LangExtract/Unstructured capabilities"""
    try:
        # LangExtract removed - using basic chunking for all cases
        if True:  # Always use basic chunking since LangExtract is removed
            # Fallback to basic chunking
            if isinstance(elements, list) and len(elements) > 0 and hasattr(elements[0], 'text'):
                text = "\n\n".join([elem.text for elem in elements if hasattr(elem, 'text')])
            elif isinstance(elements, str):
                text = elements
            else:
                text = str(elements)
            return [{"text": chunk, "metadata": {"chunk_method": "basic"}} for chunk in chunk_text_basic(text)]
        
        # Use unstructured's intelligent chunking by title/section
        chunked_elements = chunk_by_title(
            elements=elements,
            max_characters=max_characters,
            combine_text_under_n_chars=100,  # Combine very small elements
            new_after_n_chars=800  # Start new chunk after this many chars
        )
        
        chunks = []
        for i, chunk_elem in enumerate(chunked_elements):
            chunk_text = chunk_elem.text.strip()
            if chunk_text:
                # Extract metadata from the chunk element
                chunk_metadata = {
                    "chunk_method": "intelligent",
                    "chunk_index": i,
                    "element_type": str(type(chunk_elem).__name__),
                    "character_count": len(chunk_text)
                }
                
                # Add element-specific metadata if available
                if hasattr(chunk_elem, 'metadata') and chunk_elem.metadata:
                    chunk_metadata.update(chunk_elem.metadata.to_dict())
                
                chunks.append({
                    "text": chunk_text,
                    "metadata": chunk_metadata
                })
        
        logger.info(f"✅ Intelligent chunking: Created {len(chunks)} chunks from {len(elements)} elements")
        return chunks
        
    except Exception as e:
        logger.error(f"❌ Intelligent chunking failed, falling back to basic: {e}")
        # Fallback to basic chunking
        if isinstance(elements, list) and len(elements) > 0:
            if hasattr(elements[0], 'text'):
                text = "\n\n".join([elem.text for elem in elements if hasattr(elem, 'text')])
            else:
                text = "\n\n".join([str(elem) for elem in elements])
        else:
            text = str(elements)
        return [{"text": chunk, "metadata": {"chunk_method": "basic_fallback"}} for chunk in chunk_text_basic(text)]


def chunk_text_basic(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Basic text chunking (original implementation)"""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence ending in the last 100 characters
            last_period = text[max(start, end-100):end].rfind('.')
            if last_period != -1:
                end = max(start, end-100) + last_period + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start position with overlap
        start = end - overlap
        
        # Prevent infinite loop
        if start >= len(text):
            break
    
    return chunks


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Backward compatible chunking function"""
    return chunk_text_basic(text, chunk_size, overlap)

# === Vector Storage Functions ===

async def get_database_connection():
    """Get PostgreSQL database connection"""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        # Get database URL from environment
        database_url = os.getenv("POSTGRES_URL")
        if not database_url:
            raise ValueError("POSTGRES_URL environment variable not set")
        
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        return SessionLocal(), engine
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        raise

async def ensure_vector_table_exists(table_name: str):
    """Create vector table if it doesn't exist"""
    try:
        session, engine = await get_database_connection()
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR(1536),  -- OpenAI text-embedding-3-small dimension
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_id, chunk_index)
        );
        
        CREATE INDEX IF NOT EXISTS {table_name}_embedding_idx 
        ON {table_name} USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100);
        
        CREATE INDEX IF NOT EXISTS {table_name}_file_id_idx 
        ON {table_name} (file_id);
        """
        
        with engine.connect() as connection:
            connection.execute(text(create_table_sql))
            connection.commit()
        
        session.close()
        logger.info(f"✅ Vector table {table_name} ready")
        
    except Exception as e:
        logger.error(f"❌ Failed to create vector table {table_name}: {e}")
        raise

async def generate_embeddings_v2(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using OpenAI (alternative implementation)"""
    try:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        client = openai.OpenAI(api_key=openai_api_key)
        
        embeddings = []
        batch_size = 100  # OpenAI batch limit
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            response = client.embeddings.create(
                input=batch,
                model="text-embedding-3-small"
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
            
        logger.info(f"✅ Generated {len(embeddings)} embeddings")
        return embeddings
        
    except Exception as e:
        logger.error(f"❌ Failed to generate embeddings: {e}")
        raise

async def store_embeddings(
    table_name: str, 
    file_id: int, 
    chunks: List[str], 
    embeddings: List[List[float]],
    metadata: Dict = None
):
    """Store text chunks and embeddings in vector database"""
    try:
        session, engine = await get_database_connection()
        
        # Delete existing embeddings for this file
        delete_sql = f"DELETE FROM {table_name} WHERE file_id = :file_id"
        with engine.connect() as connection:
            connection.execute(text(delete_sql), {"file_id": file_id})
            connection.commit()
        
        # Insert new embeddings
        insert_sql = f"""
        INSERT INTO {table_name} (file_id, chunk_index, content, embedding, metadata)
        VALUES (:file_id, :chunk_index, :content, :embedding, :metadata)
        """
        
        with engine.connect() as connection:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                connection.execute(text(insert_sql), {
                    "file_id": file_id,
                    "chunk_index": i,
                    "content": chunk,
                    "embedding": embedding,
                    "metadata": metadata or {}
                })
            connection.commit()
        
        session.close()
        logger.info(f"✅ Stored {len(chunks)} chunks for file {file_id} in {table_name}")
        
    except Exception as e:
        logger.error(f"❌ Failed to store embeddings: {e}")
        raise

async def search_similar_content_v2(
    table_name: str,
    query_text: str,
    limit: int = 5,
    file_ids: List[int] = None
) -> List[Dict]:
    """Search for similar content using vector similarity (alternative implementation)"""
    try:
        # First ensure the table exists
        await ensure_vector_table_exists(table_name)
        
        # Generate embedding for query
        embedding_result = await generate_embeddings([query_text])
        
        # Handle different return formats from generate_embeddings functions
        if isinstance(embedding_result, dict) and "embeddings" in embedding_result:
            query_embedding = embedding_result["embeddings"][0]
        elif isinstance(embedding_result, list):
            query_embedding = embedding_result[0]
        else:
            raise ValueError(f"Unexpected embedding result format: {type(embedding_result)}")
        
        session, engine = await get_database_connection()
        
        # Check if table exists and has data with schema prefix
        try:
            check_sql = f"""
                SELECT COUNT(*) as row_count 
                FROM {SCHEMA_NAME}.{table_name}
            """
            with engine.connect() as connection:
                result = connection.execute(text(check_sql))
                row = result.fetchone()
                row_count = row[0] if row else 0
                
                if row_count == 0:
                    logger.warning(f"Table {SCHEMA_NAME}.{table_name} exists but has no data")
                    return []
                    
        except Exception as e:
            logger.warning(f"Table {SCHEMA_NAME}.{table_name} does not exist or is inaccessible: {e}")
            return []
        
        # Build search query with schema prefix
        where_clause = ""
        params = {
            "query_embedding": query_embedding,
            "limit": limit
        }
        
        if file_ids:
            placeholders = ",".join([f":file_id_{i}" for i in range(len(file_ids))])
            where_clause = f"WHERE (metadata->>'file_id')::int IN ({placeholders})"
            for i, file_id in enumerate(file_ids):
                params[f"file_id_{i}"] = file_id
        
        search_sql = f"""
        SELECT 
            (metadata->>'file_id')::int as file_id,
            (metadata->>'chunk_index')::int as chunk_index,
            content,
            metadata,
            1 - (embedding <=> :query_embedding::vector) as similarity_score
        FROM {SCHEMA_NAME}.{table_name}
        {where_clause}
        ORDER BY embedding <=> :query_embedding::vector
        LIMIT :limit
        """
        
        with engine.connect() as connection:
            result = connection.execute(text(search_sql), params)
            rows = result.fetchall()
        
        session.close()
        
        results = []
        for row in rows:
            try:
                # Handle both tuple and Row objects
                if hasattr(row, '_mapping'):
                    # SQLAlchemy Row object with _mapping
                    row_data = row._mapping
                    results.append({
                        "file_id": row_data.get("file_id", 0) if row_data.get("file_id") is not None else 0,
                        "chunk_index": row_data.get("chunk_index", 0) if row_data.get("chunk_index") is not None else 0,
                        "content": row_data.get("content", ""),
                        "metadata": row_data.get("metadata", {}),
                        "similarity_score": float(row_data.get("similarity_score", 0))
                    })
                else:
                    # Regular tuple/sequence access
                    results.append({
                        "file_id": row[0] if row[0] is not None else 0,
                        "chunk_index": row[1] if row[1] is not None else 0,
                        "content": row[2],
                        "metadata": row[3],
                        "similarity_score": float(row[4])
                    })
            except (IndexError, KeyError, TypeError) as e:
                logger.error(f"❌ Error processing database row in search_similar_content_v2: {e}, row type: {type(row)}")
                continue
        
        logger.info(f"✅ Found {len(results)} similar content chunks")
        return results
        
    except Exception as e:
        logger.error(f"❌ Vector search failed: {e}")
        return []

# === Pydantic Models ===

class AiInsightsRequest(BaseModel):
    question: str = Field(..., description="Question about the files/folder")
    project_uuid: str = Field(..., description="Project UUID for context")
    parent_id: int = Field(default=0, description="Parent folder ID (0 for root)")
    file_ids: list[int] | None = Field(None, description="Optional specific file IDs to analyze")


class AiChatRequest(BaseModel):
    message: str = Field(..., description="User's chat message")
    project_uuid: str = Field(..., description="Project UUID for context")
    parent_id: int = Field(default=0, description="Parent folder ID (0 for root)")
    file_ids: list[int] | None = Field(None, description="Optional specific file IDs for context")
    conversation_history: list[dict] | None = Field(None, description="Previous conversation context")
    conversation_id: str | None = Field(None, description="Optional conversation ID for continuity")


class FolderSummaryRequest(BaseModel):
    project_uuid: str = Field(..., description="Project UUID")
    parent_id: int = Field(default=0, description="Parent folder ID (0 for root)")

def process_vault_file_without_progress(payload: FileIngestRequest) -> int:
    """
    Process a vault file without progress tracking to avoid calling regular file endpoints.
    This is a simplified version of process_single_file specifically for vault files.
    """
    try:
        logger.info(f"📄 Processing vault file: {payload.file_path}")

        # Step 1: Clean and validate file path
        file_path = payload.clean_file_path()

        if not GCS_BUCKET_NAME:
            raise ValueError("GCS_BUCKET_NAME is not configured")

        logger.info(f"🔍 Using cleaned path: {file_path}")

        # Extract the actual file path from the GCS URL
        if file_path.startswith("gs://"):
            parts = file_path[5:].split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid GCS path format: {file_path}")
            bucket_name, actual_path = parts
            if bucket_name != GCS_BUCKET_NAME:
                raise ValueError(f"File is in bucket {bucket_name} but service is configured for {GCS_BUCKET_NAME}")
        else:
            actual_path = file_path

        # Step 2: Initialize GCS reader with bucket and key
        reader_kwargs = {
            "bucket": GCS_BUCKET_NAME,
            "key": actual_path
        }
        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            reader_kwargs["service_account_key_path"] = CREDENTIALS_PATH

        reader = GCSReader(**reader_kwargs)

        # Step 3: Download and read file
        logger.info(f"📥 Reading file from GCS: {actual_path}")
        try:
            documents = reader.load_data()
        except Exception as e:
            error_msg = f"Failed to read file {file_path}: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not documents:
            raise ValueError(f"No documents loaded from {file_path}")

        total_docs = len(documents)
        logger.info(f"📖 Loaded {total_docs} documents from {actual_path}")

        # Step 4: Initialize embedding model and vector store
        embedding_model_name = payload.embedding_model or "text-embedding-3-small"
        embeddings = OpenAIEmbedding(model=embedding_model_name)

        # Step 5: Use LlamaIndex PGVectorStore with correct embedding dimensions
        logger.info(f"🔗 Processing {total_docs} documents with LlamaIndex PGVectorStore")

        # Get the correct embedding dimension for the model
        if embedding_model_name == "text-embedding-3-small":
            embed_dim = 1536
        elif embedding_model_name == "text-embedding-3-large":
            embed_dim = 3072
        elif embedding_model_name == "text-embedding-ada-002":
            embed_dim = 1536
        else:
            # Default to the configured dimension
            embed_dim = EMBED_DIM
            logger.warning(f"Unknown embedding model {embedding_model_name}, using default dimension {embed_dim}")

        logger.info(f"Using embedding model {embedding_model_name} with {embed_dim} dimensions")

        # Create vector store directly instead of using cached version to ensure proper setup
        from sqlalchemy import create_engine
        from sqlalchemy.ext.asyncio import create_async_engine

        # Create engines
        async_engine = create_async_engine(
            POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
            pool_size=5,
            max_overflow=0,
            pool_timeout=30,
            pool_recycle=1800,
        )
        engine = create_engine(
            POSTGRES_URL,
            pool_size=5,
            max_overflow=0,
            pool_timeout=30,
            pool_recycle=1800,
        )

        # Create vector store with explicit setup
        vector_store = PGVectorStore(
            engine=engine,
            async_engine=async_engine,
            table_name=payload.vector_table_name,
            embed_dim=embed_dim,
            schema_name=SCHEMA_NAME,
            perform_setup=True,  # This should create the table if it doesn't exist
        )

        logger.info(f"✅ Vector store created for table {payload.vector_table_name} with {embed_dim} dimensions")

        # Create storage context
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # Add vault-specific metadata to each document
        for doc in documents:
            # Build metadata for LlamaIndex format
            metadata = payload.custom_metadata.copy() if payload.custom_metadata else {}
            metadata.update({
                "doc_id": str(payload.file_uuid),
                "file_name": payload.file_path,
                "ingestion_timestamp": datetime.utcnow().isoformat(),
                "project_uuid": payload.project_id or payload.custom_metadata.get("project_uuid"),
                "vault_file": True
            })
            doc.metadata.update(metadata)

        # Create index which will automatically chunk, embed, and store documents
        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=embeddings,
            # Configure text splitter
            transformations=[
                TokenTextSplitter(
                    chunk_size=payload.chunk_size or 1000,
                    chunk_overlap=payload.chunk_overlap or 200,
                )
            ]
        )

        # Verify storage by checking the vector store
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(POSTGRES_URL)
            with engine.connect() as conn:
                # Check if documents were actually stored
                count_sql = text(f"""
                    SELECT COUNT(*) as row_count
                    FROM {SCHEMA_NAME}.{payload.vector_table_name}
                    WHERE metadata_->>'project_uuid' = :project_uuid
                """)
                result = conn.execute(count_sql, {"project_uuid": payload.project_id or payload.custom_metadata.get("project_uuid")})
                row = result.fetchone()
                stored_chunks = row[0] if row else 0
                logger.info(f"✅ Verified {stored_chunks} chunks stored in database for project {payload.project_id}")

                # Also log a sample of what was stored
                if stored_chunks > 0:
                    sample_sql = text(f"""
                        SELECT node_id, LEFT(text, 100) as text_preview, metadata_
                        FROM {SCHEMA_NAME}.{payload.vector_table_name}
                        WHERE metadata_->>'project_uuid' = :project_uuid
                        LIMIT 1
                    """)
                    result = conn.execute(sample_sql, {"project_uuid": payload.project_id or payload.custom_metadata.get("project_uuid")})
                    sample_row = result.fetchone()
                    if sample_row:
                        logger.info(f"📝 Sample stored chunk: node_id={sample_row[0]}, text_preview='{sample_row[1]}...', metadata={sample_row[2]}")

                total_chunks = stored_chunks
        except Exception as e:
            logger.warning(f"⚠️ Could not verify storage (but embedding may still have succeeded): {e}")
            # Calculate total chunks created (estimate based on text length and chunk size)
            chunk_size = payload.chunk_size or 1000
            total_text_length = sum(len(doc.text) for doc in documents)
            total_chunks = max(1, total_text_length // chunk_size)
        logger.info(f"✅ Successfully processed vault file with {total_chunks} chunks from {total_docs} documents")
        return total_chunks

    except Exception as e:
        error_msg = f"Failed to process vault file {payload.file_path}: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)


class VaultFileEmbedRequest(BaseModel):
    file_id: int = Field(..., description="Vault file ID")
    file_path: str = Field(..., description="Path to file in GCS")
    original_filename: str = Field(..., description="Original filename")
    project_uuid: str = Field(..., description="Project UUID")
    user_uuid: str = Field(None, description="User UUID who owns the file")
    file_type: str = Field(None, description="File MIME type")
    file_size: int = Field(None, description="File size in bytes")


@app.post("/embed-vault-file")
async def embed_vault_file(payload: VaultFileEmbedRequest):
    """Embed a vault file for AI insights using unified LlamaIndex processing"""
    start_time = time.time()

    try:
        logger.info(f"🔄 Embedding vault file {payload.file_id}: {payload.original_filename}")

        # Ensure unified Vault vector table exists
        await ensure_vault_vector_table_exists()

        # Create an internal FileIngestRequest to reuse existing LlamaIndex processing
        ingest_request = FileIngestRequest(
            file_path=payload.file_path,
            vector_table_name=VAULT_VECTOR_TABLE,
            file_uuid=str(payload.file_id),  # Use file_id as UUID for vault files
            link_id=None,  # No link_id for vault files
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            chunk_size=1000,
            chunk_overlap=200,
            # Add vault-specific metadata
            user_uuid=payload.user_uuid,
            team_id=None,  # Vault files are project-scoped, not team-scoped
            knowledgebase_id=None,  # No KB for vault files
            project_id=payload.project_uuid,
            custom_metadata={
                "original_filename": payload.original_filename,
                "file_type": payload.file_type,
                "file_size": payload.file_size,
                "vault_file": True,
                "project_uuid": payload.project_uuid,
                "user_uuid": payload.user_uuid
            }
        )

        # Process the file directly using vault-specific processing logic (no progress tracking)
        try:
            chunks_created = process_vault_file_without_progress(ingest_request)
        except Exception as e:
            logger.error(f"❌ Failed to process vault file {payload.file_id}: {e}")
            raise

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"✅ Successfully embedded vault file {payload.file_id} in {processing_time_ms}ms")

        return {
            "success": True,
            "file_id": payload.file_id,
            "vector_table": f"{SCHEMA_NAME}.{VAULT_VECTOR_TABLE}",
            "chunks_created": chunks_created,
            "tokens_used": 0,  # Token tracking handled by process_single_file
            "embedding_model": "text-embedding-3-small",
            "processing_time_ms": processing_time_ms
        }

    except Exception as e:
        logger.error(f"❌ Error embedding vault file {payload.file_id}: {str(e)}")
        return {
            "success": False,
            "file_id": payload.file_id,
            "error": str(e)
        }


# === Healthcheck route (for Cloud Run probe) ===
@app.get("/")
async def root():
    return {"message": "LlamaIndex GCS ingestion service is alive!"}


# === Run server locally (for dev) ===
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
