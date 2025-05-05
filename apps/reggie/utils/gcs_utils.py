import logging

import requests
from django.conf import settings
from google.cloud import storage

logger = logging.getLogger(__name__)


def get_storage_client():
    """
    Return a Google Cloud Storage client using Django settings credentials.
    """
    return storage.Client(
        project=settings.GCS_PROJECT_ID,
        credentials=settings.GCS_CREDENTIALS,
    )


def post_to_cloud_run(endpoint: str, payload: dict, timeout: int = 30):
    """
    Generic POST to Cloud Run service.
    """
    url = f"{settings.LLAMAINDEX_INGESTION_URL}{endpoint}"

    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as http_err:
        logger.error(f"HTTP error during Cloud Run call to {url}: {http_err.response.text}")
        raise
    except Exception:
        logger.exception(f"General error during Cloud Run call to {url}")
        raise


def ingest_single_file(file_path: str, vector_table_name: str, file_id: int = None, link_id: int = None):
    """
    Ingest a single file from GCS into a vector table.
    Handles various file path formats:
    - Full GCS URL: gs://bucket-name/path/to/file.pdf
    - Bucket-prefixed path: bucket-name/path/to/file.pdf
    - Relative path: path/to/file.pdf
    """
    # Clean up the file path
    if file_path.startswith('gs://'):
        # Remove gs:// and bucket name
        clean_path = file_path.replace('gs://', '')
        parts = clean_path.split('/', 1)
        if len(parts) > 1:
            file_path = parts[1]
    
    # Remove any duplicate paths and clean slashes
    path_parts = [part for part in file_path.split('/') if part and part != 'bh-reggie-media']
    file_path = '/'.join(dict.fromkeys(path_parts))
    
    logger.info(f"📤 Sending ingestion request for file: {file_path}")
    
    payload = {
        "file_path": file_path,
        "vector_table_name": vector_table_name,
    }
    if file_id:
        payload["file_id"] = file_id
    if link_id:
        payload["link_id"] = link_id
    
    return post_to_cloud_run("/ingest-file", payload, timeout=300)


def ingest_gcs_prefix(gcs_prefix: str, vector_table_name: str, file_limit: int = None):
    """
    Ingest all files under a GCS prefix into a vector table.
    Removes bucket name from prefix if present, as the ingestion service will add it.
    """
    # Remove bucket name from prefix if present
    if gcs_prefix.startswith('bh-reggie-media/'):
        gcs_prefix = gcs_prefix.replace('bh-reggie-media/', '', 1)
    
    payload = {
        "gcs_prefix": gcs_prefix,
        "vector_table_name": vector_table_name,
    }
    if file_limit:
        payload["file_limit"] = file_limit
    
    logger.info(f"📤 Sending ingestion request for prefix: {gcs_prefix}")
    return post_to_cloud_run("/ingest-gcs", payload, timeout=300)
