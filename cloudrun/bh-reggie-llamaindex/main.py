import logging
import os
import urllib.parse
import tempfile
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Any, List, Dict, Optional
from io import BytesIO
import openai

import httpx

# Text extraction libraries
try:
    import PyPDF2
    from docx import Document as DocxDocument
    from pptx import Presentation
    import openpyxl
    import tiktoken
    # LangExtract - Intelligent document processing
    import langextract
    from langextract import extract as langextract_extract
    from unstructured.partition.auto import partition
    from unstructured.partition.pdf import partition_pdf
    from unstructured.partition.docx import partition_docx
    from unstructured.partition.pptx import partition_pptx
    from unstructured.partition.xlsx import partition_xlsx
    from unstructured.chunking.title import chunk_by_title
    from unstructured.staging.base import dict_to_elements
    PDF_AVAILABLE = True
    LANGEXTRACT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some text extraction libraries not available: {e}")
    PDF_AVAILABLE = False
    LANGEXTRACT_AVAILABLE = False

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
        if not LANGEXTRACT_AVAILABLE:
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
        if not LANGEXTRACT_AVAILABLE:
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
        if not LANGEXTRACT_AVAILABLE:
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
        if not LANGEXTRACT_AVAILABLE:
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
    """Enhanced storage with per-chunk metadata from LangExtract"""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        import json
        
        engine = create_engine(POSTGRES_URL)
        Session = sessionmaker(bind=engine)
        
        # Ensure table exists
        await ensure_vault_vector_table_exists()
        
        with Session() as session:
            # Delete existing embeddings for this file (for re-indexing)
            delete_sql = text(f"""
                DELETE FROM {SCHEMA_NAME}.{VAULT_VECTOR_TABLE}
                WHERE project_uuid = :project_uuid AND file_id = :file_id
            """)
            session.execute(delete_sql, {
                "project_uuid": project_uuid,
                "file_id": file_id
            })
            
            # Insert new embeddings with enhanced metadata
            for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings)):
                # Create embedding vector string
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                
                # Combine base metadata with chunk-specific metadata
                chunk_metadata = base_metadata.copy()
                chunk_metadata["chunk_index"] = i
                chunk_metadata["chunk_length"] = len(chunk)
                
                # Add LangExtract-specific chunk metadata if available
                if i < len(chunk_metadata_list):
                    chunk_specific_meta = chunk_metadata_list[i]
                    chunk_metadata.update({
                        "langextract_chunk_method": chunk_specific_meta.get("chunk_method", "unknown"),
                        "langextract_element_type": chunk_specific_meta.get("element_type"),
                        "langextract_character_count": chunk_specific_meta.get("character_count"),
                        "langextract_metadata": chunk_specific_meta  # Store full chunk metadata
                    })
                
                # Insert with enhanced fields
                insert_sql = text(f"""
                    INSERT INTO {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} 
                    (project_uuid, user_uuid, file_id, chunk_index, content, embedding, metadata) 
                    VALUES (:project_uuid, :user_uuid, :file_id, :chunk_index, :content, CAST(:embedding AS vector), CAST(:metadata AS jsonb))
                    ON CONFLICT (project_uuid, file_id, chunk_index) 
                    DO UPDATE SET 
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                """)
                
                session.execute(insert_sql, {
                    "project_uuid": project_uuid,
                    "user_uuid": user_uuid,
                    "file_id": file_id,
                    "chunk_index": i,
                    "content": chunk,
                    "embedding": embedding_str,
                    "metadata": json.dumps(chunk_metadata)
                })
            
            session.commit()
            logger.info(f"✅ Enhanced LangExtract storage: {len(text_chunks)} embeddings for file {file_id} in project {project_uuid}")
            
    except Exception as e:
        logger.error(f"Failed to store enhanced Vault embeddings: {e}")
        raise


async def store_vault_embeddings(project_uuid: str, user_uuid: str, file_id: int, text_chunks: list, embeddings: list, metadata: dict):
    """Backward compatible vault embedding storage"""
    # Create simple chunk metadata list for backward compatibility
    chunk_metadata_list = [{"chunk_method": "basic"} for _ in text_chunks]
    await store_vault_embeddings_enhanced(project_uuid, user_uuid, file_id, text_chunks, embeddings, metadata, chunk_metadata_list)


async def search_vault_embeddings(project_uuid: str, query_text: str, limit: int = 10, file_ids: list = None, user_uuid: str = None) -> list:
    """Search for similar content in unified Vault vector database"""
    try:
        # Ensure table exists
        await ensure_vault_vector_table_exists()
        
        # Generate embedding for query
        embedding_result = await generate_embeddings([query_text])
        
        # Handle different return formats from generate_embeddings functions
        if isinstance(embedding_result, dict) and "embeddings" in embedding_result:
            query_embedding = embedding_result["embeddings"][0]
        elif isinstance(embedding_result, list):
            query_embedding = embedding_result[0]
        else:
            raise ValueError(f"Unexpected embedding result format: {type(embedding_result)}")
            
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import ProgrammingError
        engine = create_engine(POSTGRES_URL)
        
        with engine.connect() as conn:
            # Check if table has data for this project
            try:
                check_sql = text(f"""
                    SELECT COUNT(*) as row_count 
                    FROM {SCHEMA_NAME}.{VAULT_VECTOR_TABLE}
                    WHERE project_uuid = :project_uuid
                """)
                result = conn.execute(check_sql, {"project_uuid": project_uuid})
                row = result.fetchone()
                row_count = row[0] if row else 0
                
                if row_count == 0:
                    logger.warning(f"No embeddings found for project {project_uuid}")
                    return []
                    
            except ProgrammingError as e:
                logger.warning(f"Error checking embeddings: {e}")
                return []
            
            # Build WHERE clause with project filter
            where_conditions = ["project_uuid = :project_uuid"]
            params = {
                "query_embedding": embedding_str,
                "project_uuid": project_uuid,
                "limit": limit
            }
            
            # Add file filtering if specified
            if file_ids:
                placeholders = ",".join([f":file_id_{i}" for i in range(len(file_ids))])
                where_conditions.append(f"file_id IN ({placeholders})")
                for i, file_id in enumerate(file_ids):
                    params[f"file_id_{i}"] = file_id
            
            # Add user filtering if specified
            if user_uuid:
                where_conditions.append("user_uuid = :user_uuid")
                params["user_uuid"] = user_uuid
            
            where_clause = "WHERE " + " AND ".join(where_conditions)
            
            search_sql = text(f"""
                SELECT 
                    file_id,
                    chunk_index,
                    content,
                    metadata,
                    1 - (embedding <=> :query_embedding::vector) as similarity
                FROM {SCHEMA_NAME}.{VAULT_VECTOR_TABLE}
                {where_clause}
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :limit
            """)
            
            result = conn.execute(search_sql, params)
            rows = result.fetchall()
            
            results = []
            for row in rows:
                try:
                    # Handle both tuple and Row objects
                    if hasattr(row, '_mapping'):
                        # SQLAlchemy Row object with _mapping
                        row_data = row._mapping
                        results.append({
                            "file_id": row_data["file_id"],
                            "chunk_index": row_data["chunk_index"], 
                            "content": row_data["content"],
                            "metadata": row_data["metadata"],
                            "similarity": float(row_data["similarity"])
                        })
                    else:
                        # Regular tuple/sequence access
                        results.append({
                            "file_id": row[0],
                            "chunk_index": row[1],
                            "content": row[2],
                            "metadata": row[3],
                            "similarity": float(row[4])
                        })
                except (IndexError, KeyError, TypeError) as e:
                    logger.error(f"❌ Error processing database row: {e}, row type: {type(row)}, row: {row}")
                    continue
            
            logger.info(f"✅ Found {len(results)} similar chunks for project {project_uuid}")
            return results
            
    except Exception as e:
        logger.error(f"Failed to search Vault embeddings: {e}")
        return []


async def generate_ai_response(question: str, context: str, prompt_type: str = "chat") -> dict:
    """Generate AI response using OpenAI GPT"""
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Create appropriate system prompt based on type
        if prompt_type == "insights":
            system_prompt = """You are an AI assistant that analyzes documents and provides insights. 
            Based on the provided context from document chunks, answer the user's question with detailed analysis.
            Focus on key insights, patterns, and important information found in the documents."""
        else:  # chat
            system_prompt = """You are an AI assistant that helps users understand their documents. 
            Answer questions based on the provided context from their document collection.
            Be helpful, accurate, and reference the source material when relevant."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context from documents:\n{context}\n\nQuestion: {question}"}
        ]
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        return {
            "response": response.choices[0].message.content,
            "tokens_used": response.usage.total_tokens
        }
        
    except Exception as e:
        logger.error(f"Failed to generate AI response: {e}")
        raise


async def generate_ai_response_stream(question: str, context: str, prompt_type: str = "chat"):
    """Generate streaming AI response using OpenAI GPT"""
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Create appropriate system prompt based on type
        if prompt_type == "insights":
            system_prompt = """You are an AI assistant that analyzes documents and provides insights. 
            Based on the provided context from document chunks, answer the user's question with detailed analysis.
            Focus on key insights, patterns, and important information found in the documents."""
        else:  # chat
            system_prompt = """You are an AI assistant that helps users understand their documents. 
            Answer questions based on the provided context from their document collection.
            Be helpful, accurate, and reference the source material when relevant."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context from documents:\n{context}\n\nQuestion: {question}"}
        ]
        
        # Create streaming response
        stream = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
            stream=True
        )
        
        # Yield chunks as they arrive
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
        
    except Exception as e:
        logger.error(f"Failed to generate streaming AI response: {e}")
        yield f"Error generating response: {str(e)}"


async def ensure_vault_vector_table_exists():
    """Ensure unified Vault vector table exists in PostgreSQL with proper schema"""
    try:
        from sqlalchemy import create_engine, text
        
        engine = create_engine(POSTGRES_URL)
        
        with engine.connect() as conn:
            # Create schema if it doesn't exist
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))
            
            # Create unified Vault embeddings table if it doesn't exist
            create_table_sql = text(f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} (
                    id BIGSERIAL PRIMARY KEY,
                    project_uuid UUID NOT NULL,
                    user_uuid UUID,
                    file_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding VECTOR(1536) NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_uuid, file_id, chunk_index)
                );
            """)
            conn.execute(create_table_sql)
            
            # Create indexes for efficient querying
            indexes = [
                f"CREATE INDEX IF NOT EXISTS {VAULT_VECTOR_TABLE}_project_uuid_idx ON {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} (project_uuid);",
                f"CREATE INDEX IF NOT EXISTS {VAULT_VECTOR_TABLE}_file_id_idx ON {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} (file_id);",
                f"CREATE INDEX IF NOT EXISTS {VAULT_VECTOR_TABLE}_user_uuid_idx ON {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} (user_uuid);",
                f"CREATE INDEX IF NOT EXISTS {VAULT_VECTOR_TABLE}_embedding_idx ON {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);",
                f"CREATE INDEX IF NOT EXISTS {VAULT_VECTOR_TABLE}_metadata_idx ON {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} USING gin (metadata);"
            ]
            
            for index_sql in indexes:
                conn.execute(text(index_sql))
            
            conn.commit()
            logger.info(f"✅ Ensured unified Vault vector table {SCHEMA_NAME}.{VAULT_VECTOR_TABLE} exists")
            
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
        if not LANGEXTRACT_AVAILABLE or not elements:
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

# === AI Response Generation ===

async def generate_ai_response_v2(context: str, question: str) -> str:
    """Generate AI response using OpenAI"""
    try:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        client = openai.OpenAI(api_key=openai_api_key)
        
        system_prompt = """You are a helpful AI assistant that analyzes documents and answers questions based on the provided context. 
        Use only the information from the provided context to answer questions. 
        If the context doesn't contain enough information to answer the question, say so clearly.
        Provide specific references to the documents when possible."""
        
        user_prompt = f"""Context from documents:
        {context}
        
        Question: {question}
        
        Please provide a comprehensive answer based on the context provided."""
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1000,
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"❌ Failed to generate AI response: {e}")
        return f"Failed to generate response: {str(e)}"

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


@app.post("/ai-insights")
async def generate_ai_insights(payload: AiInsightsRequest):
    """Generate AI insights for vault files based on a question"""
    start_time = time.time()
    
    try:
        logger.info(f"🤖 Generating AI insights for project {payload.project_uuid}, question: {payload.question[:100]}")
        
        # Use unified Vault embeddings table
        search_results = await search_vault_embeddings(
            project_uuid=payload.project_uuid,
            query_text=payload.question,
            limit=10,
            file_ids=payload.file_ids
        )
        
        if not search_results:
            return {
                "response": "No relevant content found for your question. This might be because the files haven't been embedded yet or there's no matching content.",
                "insights": {
                    "summary": "No relevant documents found",
                    "key_points": ["No matching content in the vector database"],
                    "file_types": [],
                    "suggestions": [
                        "Try rephrasing your question",
                        "Ensure files have been processed and embedded",
                        "Check if the files contain relevant content"
                    ]
                },
                "processed_files_count": 0,
                "vector_table_used": f"{SCHEMA_NAME}.{VAULT_VECTOR_TABLE}",
                "tokens_used": 0,
                "response_time_ms": int((time.time() - start_time) * 1000)
            }
        
        # Extract relevant content and metadata
        relevant_content = []
        file_types = set()
        unique_files = set()
        
        for result in search_results:
            relevant_content.append(result["content"])
            if result.get("metadata", {}).get("original_filename"):
                file_ext = os.path.splitext(result["metadata"]["original_filename"])[1].upper()
                if file_ext:
                    file_types.add(file_ext[1:])  # Remove the dot
            if result.get("metadata", {}).get("file_id"):
                unique_files.add(result["metadata"]["file_id"])
        
        # Generate AI insights based on retrieved content
        context = "\n\n".join(relevant_content[:5])  # Use top 5 results for context
        
        ai_response = await generate_ai_response(
            question=payload.question,
            context=context,
            prompt_type="insights"
        )
        
        # Parse the AI response
        response_data = ai_response["response"]
        tokens_used = ai_response["tokens_used"]
        
        # Create structured insights
        insights = {
            "summary": f"Based on vector search analysis of {len(unique_files)} files, I found {len(search_results)} relevant content sections with similarity scores ranging from {search_results[0]['similarity']:.3f} to {search_results[-1]['similarity']:.3f}.",
            "key_points": [
                f"Analyzed {len(search_results)} content chunks from {len(unique_files)} unique files",
                f"Highest similarity score: {search_results[0]['similarity']:.3f}",
                f"Content types: {', '.join(file_types) if file_types else 'Mixed'}",
                "AI analysis based on most relevant content sections"
            ],
            "file_types": list(file_types),
            "suggestions": [
                "Review the AI analysis for key insights",
                "Check the source files for more detailed information",
                "Ask follow-up questions for deeper analysis"
            ]
        }
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"✅ Generated AI insights in {processing_time_ms}ms with {tokens_used} tokens")
        
        return {
            "response": response_data,
            "insights": insights,
            "processed_files_count": len(unique_files),
            "vector_table_used": f"{SCHEMA_NAME}.{VAULT_VECTOR_TABLE}",
            "tokens_used": tokens_used,
            "response_time_ms": processing_time_ms
        }
        
    except Exception as e:
        logger.error(f"❌ Error generating AI insights: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/ai-chat")
async def ai_chat(payload: AiChatRequest):
    """Handle AI chat conversations about vault files"""
    start_time = time.time()
    
    try:
        logger.info(f"💬 AI chat request for project {payload.project_uuid}: {payload.message[:100]}")
        
        # Build context from conversation history if provided
        conversation_context = ""
        if payload.conversation_history:
            # Include last few messages for context
            recent_messages = payload.conversation_history[-5:]  # Last 5 messages
            conversation_context = "\n".join([
                f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
                for msg in recent_messages
            ])
        
        # Use unified Vault embeddings table for search
        search_results = await search_vault_embeddings(
            project_uuid=payload.project_uuid,
            query_text=payload.message,
            limit=8,
            file_ids=payload.file_ids
        )
        
        sources = []
        relevant_content = []
        
        if search_results:
            # Build sources array with actual results
            for i, result in enumerate(search_results):
                metadata = result.get("metadata", {})
                sources.append({
                    "file_id": metadata.get("file_id", f"unknown_{i}"),
                    "file_name": metadata.get("original_filename", f"document_{i}.pdf"),
                    "relevance_score": result["similarity"],
                    "excerpt": result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"]
                })
                relevant_content.append(result["content"])
        
        # Generate response using AI model with retrieved context
        context = "\n\n".join(relevant_content[:5])  # Use top 5 results for context
        
        # Add conversation context if available
        if conversation_context:
            context = f"Previous conversation:\n{conversation_context}\n\nRelevant documents:\n{context}"
        
        ai_response = await generate_ai_response(
            question=payload.message,
            context=context,
            prompt_type="chat"
        )
        
        response_data = ai_response["response"]
        tokens_used = ai_response["tokens_used"]
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Generate conversation ID if not provided
        conversation_id = payload.conversation_id or f"conv_{payload.project_uuid}_{payload.parent_id}_{int(time.time())}"
        
        # Generate suggested follow-ups based on content
        suggested_followups = [
            "Can you elaborate on that point?",
            "What are the key takeaways?",
            "How does this relate to other documents?"
        ]
        
        if sources:
            suggested_followups = [
                "Tell me more about the specific files mentioned",
                "What are the main insights from these documents?",
                "How do these findings connect together?"
            ]
        
        logger.info(f"✅ Generated AI chat response in {processing_time_ms}ms with {tokens_used} tokens")
        
        return {
            "response": response_data,
            "conversation_id": conversation_id,
            "sources": sources,
            "vector_table_used": f"{SCHEMA_NAME}.{VAULT_VECTOR_TABLE}",
            "tokens_used": tokens_used,
            "response_time_ms": processing_time_ms,
            "suggested_followups": suggested_followups
        }
        
    except Exception as e:
        logger.error(f"❌ Error in AI chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/ai-chat-stream")
async def ai_chat_stream(payload: AiChatRequest):
    """Handle AI chat conversations with streaming responses"""
    from fastapi.responses import StreamingResponse
    import json
    
    try:
        logger.info(f"💬 Streaming AI chat request for project {payload.project_uuid}: {payload.message[:100]}")
        
        async def generate_stream():
            start_time = time.time()
            
            # Build context from conversation history if provided
            conversation_context = ""
            if payload.conversation_history:
                recent_messages = payload.conversation_history[-5:]
                conversation_context = "\n".join([
                    f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
                    for msg in recent_messages
                ])
            
            # Use unified Vault embeddings table for search
            search_results = await search_vault_embeddings(
                project_uuid=payload.project_uuid,
                query_text=payload.message,
                limit=8,
                file_ids=payload.file_ids
            )
            
            sources = []
            relevant_content = []
            
            if search_results:
                for i, result in enumerate(search_results):
                    metadata = result.get("metadata", {})
                    sources.append({
                        "file_id": metadata.get("file_id", f"unknown_{i}"),
                        "file_name": metadata.get("original_filename", f"document_{i}.pdf"),
                        "relevance_score": result["similarity"],
                        "excerpt": result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"]
                    })
                    relevant_content.append(result["content"])
            
            # Send sources first
            yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
            
            # Generate conversation ID if not provided
            conversation_id = payload.conversation_id or f"conv_{payload.project_uuid}_{payload.parent_id}_{int(time.time())}"
            yield f"data: {json.dumps({'type': 'conversation_id', 'data': conversation_id})}\n\n"
            
            # Prepare context for AI
            context = "\n\n".join(relevant_content[:5])
            if conversation_context:
                context = f"Previous conversation:\n{conversation_context}\n\nRelevant documents:\n{context}"
            
            # Stream AI response
            async for chunk in generate_ai_response_stream(
                question=payload.message,
                context=context,
                prompt_type="chat"
            ):
                yield f"data: {json.dumps({'type': 'content', 'data': chunk})}\n\n"
            
            # Send completion metadata
            processing_time_ms = int((time.time() - start_time) * 1000)
            suggested_followups = [
                "Tell me more about the specific files mentioned",
                "What are the main insights from these documents?",
                "How do these findings connect together?"
            ] if sources else [
                "Can you elaborate on that point?",
                "What are the key takeaways?",
                "How does this relate to other documents?"
            ]
            
            completion_data = {
                "type": "completion",
                "data": {
                    "vector_table_used": f"{SCHEMA_NAME}.{VAULT_VECTOR_TABLE}",
                    "response_time_ms": processing_time_ms,
                    "suggested_followups": suggested_followups
                }
            }
            yield f"data: {json.dumps(completion_data)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error in streaming AI chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/folder-summary")
async def generate_folder_summary(payload: FolderSummaryRequest):
    """Generate AI summary for a folder's contents"""
    try:
        logger.info(f"📁 Generating folder summary for project {payload.project_uuid}, folder {payload.parent_id}")
        
        # TODO: Get all files in the folder
        # TODO: Analyze file types and content
        # TODO: Generate comprehensive folder summary
        
        # Mock response for now
        return {
            "summary": "This folder contains a collection of business documents including contracts, reports, and presentations. The documents appear to be related to project management and client communications.",
            "file_count": 12,
            "folder_count": 3,
            "file_types": ["PDF", "DOCX", "XLSX", "PPTX"],
            "key_insights": [
                "Most documents are from the last 6 months",
                "Primary focus on client project deliverables",
                "Contains both internal and external communications"
            ],
            "tokens_used": 180,
            "processing_time_ms": 900
        }
        
    except Exception as e:
        logger.error(f"❌ Error generating folder summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/analyze-file-content")
async def analyze_file_content(file_id: int, analysis_type: str = "full"):
    """Analyze a specific file's content for insights"""
    try:
        logger.info(f"🔍 Analyzing file content for file ID: {file_id}")
        
        # TODO: Get file from storage
        # TODO: Extract text content
        # TODO: Generate insights based on analysis_type
        
        # Mock response for now
        return {
            "file_id": file_id,
            "insights": {
                "summary": "This document contains important business information with key metrics and recommendations.",
                "key_points": [
                    "Revenue increased by 15% this quarter",
                    "Customer satisfaction scores improved",
                    "Recommendations for next quarter planning"
                ],
                "entities": {
                    "people": ["John Doe", "Jane Smith"],
                    "dates": ["2024-01-15", "2024-03-30"],
                    "monetary_values": ["$150,000", "$45,000"]
                },
                "document_type": "business_report",
                "confidence_score": 0.92
            },
            "processing_status": "completed",
            "tokens_used": 250,
            "processed_at": "2024-01-10T10:00:00Z"
        }
        
    except Exception as e:
        logger.error(f"❌ Error analyzing file content: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
    """Embed a vault file for AI insights"""
    start_time = time.time()
    tokens_used = 0
    chunks_created = 0
    
    try:
        logger.info(f"🔄 Embedding vault file {payload.file_id}: {payload.original_filename}")
        
        # Ensure unified Vault vector table exists
        await ensure_vault_vector_table_exists()
        
        # Download file from GCS
        file_content = download_gcs_file(payload.file_path)
        if not file_content:
            raise Exception(f"Failed to download file from GCS: {payload.file_path}")
        
        # Enhanced text extraction using LangExtract with structure-aware processing
        file_extension = os.path.splitext(payload.original_filename)[1].lower()
        logger.info(f"🔄 Processing {payload.original_filename} ({file_extension}) with LangExtract")
        
        # Use enhanced extraction that returns both text and structural metadata
        text_content, extraction_metadata = extract_text_from_file_langextract(
            file_content, payload.file_type, payload.original_filename
        )
        
        if not text_content or not text_content.strip():
            raise Exception("No text content extracted from file")
        
        logger.info(f"📄 LangExtract extracted {len(text_content)} characters from {payload.original_filename}")
        logger.info(f"📊 Document structure: {len(extraction_metadata.get('document_structure', []))} elements")
        
        # Try intelligent chunking first, fallback to basic if needed
        text_chunks = []
        chunk_metadata_list = []
        
        if LANGEXTRACT_AVAILABLE and extraction_metadata.get('document_structure'):
            logger.info("🧠 Attempting intelligent chunking with LangExtract")
            try:
                # For intelligent chunking, we need to re-extract the elements if available
                if file_extension == '.pdf':
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                        tmp_file.write(file_content)
                        tmp_file.flush()
                        elements = partition_pdf(tmp_file.name, strategy="hi_res", infer_table_structure=True)
                        os.unlink(tmp_file.name)
                elif file_extension in ['.docx', '.doc']:
                    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
                        tmp_file.write(file_content)
                        tmp_file.flush()
                        elements = partition_docx(tmp_file.name, infer_table_structure=True)
                        os.unlink(tmp_file.name)
                elif file_extension in ['.pptx', '.ppt']:
                    with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp_file:
                        tmp_file.write(file_content)
                        tmp_file.flush()
                        elements = partition_pptx(tmp_file.name)
                        os.unlink(tmp_file.name)
                elif file_extension in ['.xlsx', '.xls']:
                    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                        tmp_file.write(file_content)
                        tmp_file.flush()
                        elements = partition_xlsx(tmp_file.name)
                        os.unlink(tmp_file.name)
                else:
                    elements = None
                
                if elements:
                    # Use intelligent chunking
                    intelligent_chunks = chunk_text_intelligent(elements, max_characters=1000)
                    for chunk_data in intelligent_chunks:
                        if chunk_data['text'].strip():
                            text_chunks.append(chunk_data['text'])
                            chunk_metadata_list.append(chunk_data['metadata'])
                    
                    logger.info(f"🧠 Intelligent chunking created {len(text_chunks)} chunks")
                else:
                    raise Exception("No elements available for intelligent chunking")
                    
            except Exception as e:
                logger.warning(f"⚠️ Intelligent chunking failed, falling back to basic: {e}")
                # Fallback to basic chunking
                basic_chunks = chunk_text_basic(text_content, chunk_size=1000, overlap=200)
                text_chunks = basic_chunks
                chunk_metadata_list = [{"chunk_method": "basic_fallback"} for _ in basic_chunks]
        else:
            # Basic chunking
            logger.info("📝 Using basic chunking")
            basic_chunks = chunk_text_basic(text_content, chunk_size=1000, overlap=200)
            text_chunks = basic_chunks
            chunk_metadata_list = [{"chunk_method": "basic"} for _ in basic_chunks]
        
        chunks_created = len(text_chunks)
        logger.info(f"📝 Created {chunks_created} text chunks")
        
        if chunks_created == 0:
            raise Exception("No valid text chunks created")
        
        # Generate embeddings and store in database
        embedding_results = await generate_embeddings(text_chunks)
        
        # Handle different return formats from generate_embeddings functions
        if isinstance(embedding_results, dict):
            embeddings = embedding_results["embeddings"]
            tokens_used = embedding_results.get("tokens_used", 0)
        elif isinstance(embedding_results, list):
            embeddings = embedding_results
            tokens_used = 0  # Token count not available from list format
        else:
            raise ValueError(f"Unexpected embedding result format: {type(embedding_results)}")
        
        # Store embeddings with enhanced metadata in unified table
        base_metadata = {
            "file_path": payload.file_path,
            "original_filename": payload.original_filename,
            "file_type": payload.file_type,
            "file_size": payload.file_size,
            "processed_at": datetime.now().isoformat(),
            "langextract_enabled": LANGEXTRACT_AVAILABLE,
            "extraction_metadata": extraction_metadata  # Include structural information
        }
        
        # Enhanced storage with per-chunk metadata
        await store_vault_embeddings_enhanced(
            project_uuid=payload.project_uuid,
            user_uuid=payload.user_uuid,
            file_id=payload.file_id,
            text_chunks=text_chunks,
            embeddings=embeddings,
            base_metadata=base_metadata,
            chunk_metadata_list=chunk_metadata_list
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"✅ Successfully embedded vault file {payload.file_id} with {chunks_created} chunks in {processing_time_ms}ms")
        
        return {
            "success": True,
            "file_id": payload.file_id,
            "vector_table": f"{SCHEMA_NAME}.{VAULT_VECTOR_TABLE}",
            "chunks_created": chunks_created,
            "tokens_used": tokens_used,
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
