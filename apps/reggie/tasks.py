import logging
import threading

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
        f"Calling LlamaIndex service to delete vectors. URL: {endpoint}, Payload: {payload}, Headers: {{'Authorization': 'Api-Key {masked_api_key}', ...}}"
    )

    try:
        with httpx.Client(timeout=30.0) as client:  # Using httpx.Client for synchronous context in Celery task
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx responses
            logger.info(
                f"Successfully deleted vectors for file_uuid: {file_uuid} from table: {vector_table_name}. Response: {response.json()}"
            )
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error calling LlamaIndex service for vector deletion: {e.response.status_code} "
            f"Response: {e.response.text}. File UUID: {file_uuid}, Table: {vector_table_name}"
        )
    except httpx.RequestError as e:
        logger.error(
            f"Request error calling LlamaIndex service for vector deletion: {str(e)}. File UUID: {file_uuid}, Table: {vector_table_name}"
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while trying to delete vectors via LlamaIndex service: {str(e)}. File UUID: {file_uuid}, Table: {vector_table_name}"
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
                f"Dispatching task for file_uuid: {file_info.get('file_uuid')}, original_filename: {file_info.get('original_filename')}"
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
                        f"Failed to update FileKnowledgeBaseLink status for link_id {link_id} after dispatch error: {db_error}",
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

        def fire_and_forget_ingestion(ingestion_url, payload, headers):
            with httpx.Client(timeout=60.0) as client:
                client.post(ingestion_url, json=payload, headers=headers)

        thread = threading.Thread(target=fire_and_forget_ingestion, args=(ingestion_url, payload, headers), daemon=True)
        thread.start()

        return "Ingestion triggered successfully"

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


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60})
def embed_vault_file_task(self, vault_file_id):
    """
    Celery task to embed a vault file for AI insights
    """
    from .models import VaultFile, Project
    from .utils.gcs_utils import post_to_cloud_run
    
    try:
        # Get the vault file
        vault_file = VaultFile.objects.get(id=vault_file_id)
        logger.info(f"🔄 Starting embedding for vault file {vault_file.id}: {vault_file.original_filename}")
        
        # Ensure project exists
        project = vault_file.project
        if not project:
            raise ValueError(f"Vault file {vault_file.id} has no associated project")
        
        # Prepare payload for Cloud Run service (unified table approach)
        payload = {
            "file_id": vault_file.id,
            "file_path": vault_file.file.name if vault_file.file else None,
            "original_filename": vault_file.original_filename,
            "project_uuid": str(project.uuid),
            "user_uuid": str(vault_file.uploaded_by.uuid) if vault_file.uploaded_by else None,
            "file_type": vault_file.type,
            "file_size": vault_file.size
        }
        
        # Call Cloud Run service to embed the file
        logger.info(f"📤 Sending embedding request to Cloud Run for file {vault_file.id}")
        response = post_to_cloud_run("/embed-vault-file", payload, timeout=120)
        
        # Update vault file status based on response
        vault_file.embedding_status = "completed" if response.get("success") else "failed"
        vault_file.is_embedded = response.get("success", False)
        vault_file.embedded_at = timezone.now() if response.get("success") else None
        vault_file.embedding_error = response.get("error") if not response.get("success") else None
        
        vault_file.save(update_fields=[
            "embedding_status", "is_embedded", "embedded_at", "embedding_error"
        ])
        
        if response.get("success"):
            logger.info(f"✅ Successfully embedded vault file {vault_file.id}")
        else:
            logger.error(f"❌ Failed to embed vault file {vault_file.id}: {response.get('error')}")
            
        return {"success": response.get("success"), "file_id": vault_file.id}
        
    except VaultFile.DoesNotExist:
        logger.error(f"❌ VaultFile with ID {vault_file_id} not found")
        raise
        
    except Exception as e:
        # Update file status to failed
        try:
            vault_file = VaultFile.objects.get(id=vault_file_id)
            vault_file.embedding_status = "failed"
            vault_file.embedding_error = f"Embedding task failed: {str(e)}"
            vault_file.save(update_fields=["embedding_status", "embedding_error"])
        except:
            pass
            
        logger.error(f"❌ Embedding task failed for vault file {vault_file_id}: {e}")
        raise
