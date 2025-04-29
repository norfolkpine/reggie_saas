import requests
import logging
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
    url = f"{settings.CLOUD_RUN_BASE_URL}{endpoint}"

    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as http_err:
        logger.error(f"HTTP error during Cloud Run call to {url}: {http_err.response.text}")
        raise
    except Exception as e:
        logger.exception(f"General error during Cloud Run call to {url}")
        raise

def ingest_single_file(file_path: str, vector_table_name: str):
    """
    Trigger ingestion of a single file into the knowledge base.
    """
    payload = {
        "file_path": file_path,
        "vector_table_name": vector_table_name,
    }
    return post_to_cloud_run("/ingest-file", payload)

def ingest_gcs_prefix(gcs_prefix: str, vector_table_name: str, file_limit: int = 1000):
    """
    Trigger ingestion of all files under a GCS prefix (bulk ingestion).
    """
    payload = {
        "gcs_prefix": gcs_prefix,
        "vector_table_name": vector_table_name,
        "file_limit": file_limit,
    }
    return post_to_cloud_run("/ingest-gcs", payload)
