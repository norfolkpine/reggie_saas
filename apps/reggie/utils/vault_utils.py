import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def embed_vault_file(
    file_path: str,
    file_id: int,
    original_filename: str,
    project_uuid: str,
    user_uuid: str,
    file_type: str = None,
    file_size: int = None,
    timeout: int = 300,
) -> dict:
    """
    Embed a vault file using the unified LlamaIndex service.
    This replaces the old LangExtract-based processing.
    """
    if not hasattr(settings, "LLAMAINDEX_INGESTION_URL") or not settings.LLAMAINDEX_INGESTION_URL:
        logger.error("LLAMAINDEX_INGESTION_URL is not configured in Django settings")
        raise ValueError("LLAMAINDEX_INGESTION_URL is not configured")

    service_url = settings.LLAMAINDEX_INGESTION_URL.rstrip("/")
    endpoint = f"{service_url}/embed-vault-file"

    payload = {
        "file_path": file_path,
        "file_id": file_id,
        "original_filename": original_filename,
        "project_uuid": project_uuid,
        "user_uuid": user_uuid,
        "file_type": file_type,
        "file_size": file_size,
    }

    # Use API key if configured
    headers = {"Content-Type": "application/json"}
    api_key = getattr(settings, "SYSTEM_API_KEY", None)
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"

    try:
        logger.info(f"📤 Sending vault embedding request for file: {original_filename} (ID: {file_id})")

        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()

        result = response.json()
        logger.info(f"✅ Successfully embedded vault file {file_id}: {result.get('chunks_created', 0)} chunks created")

        return result

    except requests.HTTPError as http_err:
        logger.error(f"HTTP error embedding vault file {file_id}: {http_err.response.text}")
        raise
    except Exception as e:
        logger.error(f"Error embedding vault file {file_id}: {str(e)}")
        raise


def delete_vault_file_vectors(file_uuid: str, timeout: int = 30) -> dict:
    """
    Delete vault file vectors from the vector database.
    """
    if not hasattr(settings, "LLAMAINDEX_INGESTION_URL") or not settings.LLAMAINDEX_INGESTION_URL:
        logger.error("LLAMAINDEX_INGESTION_URL is not configured in Django settings")
        raise ValueError("LLAMAINDEX_INGESTION_URL is not configured")

    service_url = settings.LLAMAINDEX_INGESTION_URL.rstrip("/")
    endpoint = f"{service_url}/delete-vectors"

    # Use vault vector table name
    vault_table_name = getattr(settings, "VAULT_PGVECTOR_TABLE", "vault_vector_table")

    payload = {"vector_table_name": vault_table_name, "file_uuid": file_uuid}

    headers = {"Content-Type": "application/json"}
    api_key = getattr(settings, "SYSTEM_API_KEY", None)
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"

    try:
        logger.info(f"🗑️ Deleting vault vectors for file_uuid: {file_uuid}")

        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()

        result = response.json()
        logger.info(f"✅ Successfully deleted {result.get('deleted_count', 0)} vectors for file_uuid: {file_uuid}")

        return result

    except requests.HTTPError as http_err:
        logger.error(f"HTTP error deleting vault vectors for {file_uuid}: {http_err.response.text}")
        raise
    except Exception as e:
        logger.error(f"Error deleting vault vectors for {file_uuid}: {str(e)}")
        raise
