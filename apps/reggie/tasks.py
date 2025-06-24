import logging

import httpx
from celery import shared_task
from django.conf import settings
from django.utils import timezone  # Added for timezone.now()

logger = logging.getLogger(__name__)


@shared_task
def delete_vectors_from_llamaindex_task(vector_table_name: str, file_uuid: str):
    """
    Asynchronously calls the LlamaIndex service to delete vectors
    associated with a specific file_uuid from a given vector_table_name.
    """
    if not hasattr(settings, "LLAMAINDEX_SERVICE_URL") or not settings.LLAMAINDEX_SERVICE_URL:
        logger.error("LLAMAINDEX_SERVICE_URL is not configured in Django settings. Cannot delete vectors.")
        return

    if not hasattr(settings, "DJANGO_API_KEY_FOR_LLAMAINDEX") or not settings.DJANGO_API_KEY_FOR_LLAMAINDEX:
        logger.error(
            "DJANGO_API_KEY_FOR_LLAMAINDEX is not configured in Django settings. Cannot call LlamaIndex service."
        )
        return

    service_url = settings.LLAMAINDEX_SERVICE_URL.rstrip("/")
    endpoint = f"{service_url}/delete-vectors"

    payload = {"vector_table_name": vector_table_name, "file_uuid": file_uuid}

    api_key = settings.DJANGO_API_KEY_FOR_LLAMAINDEX
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",  # Good practice to include Accept header
    }

    masked_api_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 7 else "key_too_short_to_mask"
    logger.info(
        f"Calling LlamaIndex service to delete vectors. URL: {endpoint}, "
        f"Payload: {payload}, Headers: {{'Authorization': 'Api-Key {masked_api_key}', ...}}"
    )

    try:
        with httpx.Client(timeout=30.0) as client:  # Using httpx.Client for synchronous context in Celery task
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


@shared_task(bind=True)
def dispatch_ingestion_jobs_from_batch(self, batch_file_info_list):
    from .models import FileKnowledgeBaseLink

    """
    Dispatches individual ingestion tasks for each file in the batch.
    """
    logger.info(f"Dispatching ingestion for batch of {len(batch_file_info_list)} files.")

    for file_info in batch_file_info_list:
        try:
            logger.info(
                f"Dispatching task for file_uuid: {file_info.get('file_uuid')}, "
                f"original_filename: {file_info.get('original_filename')}"
            )
            # This task will be created in the next step.
            # For now, we assume it exists or will exist in this file.
            ingest_single_file_via_http_task.delay(file_info)
        except Exception as e:
            logger.error(
                f"Failed to dispatch ingestion task for file_uuid: {file_info.get('file_uuid')}. Error: {e}",
                exc_info=True,
            )
            link_id = file_info.get("link_id")
            if link_id:
                try:
                    FileKnowledgeBaseLink.objects.filter(id=link_id).update(
                        ingestion_status="failed",
                        ingestion_error=f"Celery dispatch failed: {str(e)[:255]}",  # Truncate error
                    )
                    logger.info(f"Marked FileKnowledgeBaseLink {link_id} as failed due to dispatch error.")
                except Exception as db_error:
                    logger.error(
                        f"Failed to update FileKnowledgeBaseLink status for link_id {link_id} "
                        f"after dispatch error: {db_error}",
                        exc_info=True,
                    )

    logger.info(f"Finished dispatching all tasks for batch of {len(batch_file_info_list)} files.")


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60})
def ingest_single_file_via_http_task(self, file_info: dict):
    from .models import FileKnowledgeBaseLink

    """
    Triggers the ingestion of a single file by making an HTTP POST request to the Cloud Run service.
    Handles FileKnowledgeBaseLink status updates based on the outcome.
    """

    print("file_info", file_info.get("embedding_provider"))
    gcs_path = file_info.get("gcs_path")
    vector_table_name = file_info.get("vector_table_name")
    file_uuid = file_info.get("file_uuid")
    link_id = file_info.get("link_id")
    embedding_provider = file_info.get("embedding_provider")
    embedding_model = file_info.get("embedding_model")
    chunk_size = file_info.get("chunk_size")
    chunk_overlap = file_info.get("chunk_overlap")
    original_filename = file_info.get("original_filename", "Unknown filename")

    user_uuid = file_info.get("user_uuid")
    team_id = file_info.get("team_id")
    knowledgebase_id = file_info.get("knowledgebase_id")
    project_id = file_info.get("project_id")
    custom_metadata = file_info.get("custom_metadata")

    logger.info(
        f"Starting ingestion trigger for file: {original_filename} (UUID: {file_uuid}, Link ID: {link_id}, "
        f"Attempt: {self.request.retries + 1}/{self.max_retries + 1})"
    )

    ingestion_base_url = getattr(settings, "LLAMAINDEX_INGESTION_URL", None)
    if not ingestion_base_url:
        logger.error("LLAMAINDEX_INGESTION_URL is not configured. Cannot trigger ingestion.")
        if link_id:
            try:
                FileKnowledgeBaseLink.objects.filter(id=link_id).update(
                    ingestion_status="failed", ingestion_error="LLAMAINDEX_INGESTION_URL not configured"
                )
            except Exception as db_e:
                logger.error(f"Failed to update link {link_id} to failed: {db_e}")
        # This will be caught by the main try/except and retried by Celery
        raise ValueError("LLAMAINDEX_INGESTION_URL not configured.")

    ingestion_url = f"{ingestion_base_url.rstrip('/')}/ingest-file"

    payload = {
        "file_path": gcs_path,
        "vector_table_name": vector_table_name,
        "file_uuid": str(file_uuid) if file_uuid is not None else None,
        "link_id": str(link_id) if link_id is not None else None,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        # Add X-Request-Source if your Cloud Run service expects it for identifying the caller
        # "request_source": "reggie-celery-ingestion",
        "user_uuid": str(user_uuid) if user_uuid is not None else None,
        "team_id": str(team_id) if team_id is not None else None,
        "knowledgebase_id": str(knowledgebase_id) if knowledgebase_id is not None else None,
        "project_id": str(project_id) if project_id is not None else None,
        "custom_metadata": custom_metadata,
    }

    print(f"Payload: {payload}")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Request-Source": "reggie-celery-ingestion",  # To identify the source of the request
    }

    logger.info(f"Sending ingestion request to {ingestion_url} with payload: {payload}")

    try:
        # Note: httpx.Client is used here as a context manager for proper resource management.
        # Celery tasks are typically synchronous within their execution context, so httpx.Client is appropriate.
        if link_id:
            FileKnowledgeBaseLink.objects.filter(id=link_id).update(
                ingestion_status="processing",
                ingestion_started_at=timezone.now(),
                # Clear any previous error if this is a retry
                ingestion_error=None,
            )

        with httpx.Client(timeout=60.0) as client:  # Adjust timeout as needed, e.g., 60.0 for larger files
            response = client.post(ingestion_url, json=payload, headers=headers)

        if 200 <= response.status_code < 300:
            logger.info(
                f"Successfully triggered ingestion for file: {original_filename} (UUID: {file_uuid}). "
                f"Cloud Run response: {response.status_code}"
            )

        else:
            error_message = (
                f"Failed to trigger ingestion for file: {original_filename} (UUID: {file_uuid}). "
                f"Status: {response.status_code}, Response: {response.text[:500]}"
            )
            logger.error(error_message)
            if link_id:
                FileKnowledgeBaseLink.objects.filter(id=link_id).update(
                    ingestion_status="failed", ingestion_error=error_message[:255]
                )
            # This will raise an HTTPStatusError for 4xx/5xx, triggering Celery retry
            response.raise_for_status()

    except Exception as e:
        # This captures httpx.RequestError (network issues, timeouts), httpx.HTTPStatusError (from raise_for_status),
        # or the ValueError from missing LLAMAINDEX_INGESTION_URL.
        error_message_for_db = f"Ingestion trigger failed for {original_filename}: {str(e)[:150]}"
        logger.error(
            f"Exception in ingestion trigger for file: {original_filename} (UUID: {file_uuid}). Error: {e}",
            exc_info=True,  # Provides full traceback in logs
        )
        if link_id:
            try:
                # Update status to failed, as retries (if any) will create a new task instance
                # or if max_retries is reached.
                FileKnowledgeBaseLink.objects.filter(id=link_id).update(
                    ingestion_status="failed", ingestion_error=error_message_for_db
                )
            except Exception as db_e:
                logger.error(
                    f"Additionally, failed to update link {link_id} to 'failed' after HTTP/task error: {db_e}",
                    exc_info=True,
                )
        # Re-raise the exception. Celery's autoretry_for=(Exception,) will handle retrying it
        # based on the retry_kwargs (max_retries, countdown).
        # If max_retries is exhausted, Celery marks the task as failed.
        raise
