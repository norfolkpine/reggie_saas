from celery import shared_task
import httpx
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@shared_task
def delete_vectors_from_llamaindex_task(vector_table_name: str, file_uuid: str):
    """
    Asynchronously calls the LlamaIndex service to delete vectors
    associated with a specific file_uuid from a given vector_table_name.
    """
    if not hasattr(settings, 'LLAMAINDEX_SERVICE_URL') or not settings.LLAMAINDEX_SERVICE_URL:
        logger.error("LLAMAINDEX_SERVICE_URL is not configured in Django settings. Cannot delete vectors.")
        return

    if not hasattr(settings, 'DJANGO_API_KEY_FOR_LLAMAINDEX') or not settings.DJANGO_API_KEY_FOR_LLAMAINDEX:
        logger.error("DJANGO_API_KEY_FOR_LLAMAINDEX is not configured in Django settings. Cannot call LlamaIndex service.")
        return

    service_url = settings.LLAMAINDEX_SERVICE_URL.rstrip('/')
    endpoint = f"{service_url}/delete-vectors"

    payload = {
        "vector_table_name": vector_table_name,
        "file_uuid": file_uuid
    }

    api_key = settings.DJANGO_API_KEY_FOR_LLAMAINDEX
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json", # Good practice to include Accept header
    }

    masked_api_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 7 else "key_too_short_to_mask"
    logger.info(
        f"Calling LlamaIndex service to delete vectors. URL: {endpoint}, "
        f"Payload: {payload}, Headers: {{'Authorization': 'Api-Key {masked_api_key}', ...}}"
    )

    try:
        with httpx.Client(timeout=30.0) as client: # Using httpx.Client for synchronous context in Celery task
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx responses
            logger.info(
                f"Successfully deleted vectors for file_uuid: {file_uuid} from table: {vector_table_name}. "
                f"Response: {response.json()}"
            )
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error calling LlamaIndex service for vector deletion: {e.response.status_code} "
            f"Response: {e.response.text}. File UUID: {file_uuid}, Table: {vector_table_name}"
        )
    except httpx.RequestError as e:
        logger.error(
            f"Request error calling LlamaIndex service for vector deletion: {str(e)}. "
            f"File UUID: {file_uuid}, Table: {vector_table_name}"
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while trying to delete vectors via LlamaIndex service: {str(e)}. "
            f"File UUID: {file_uuid}, Table: {vector_table_name}"
        )
