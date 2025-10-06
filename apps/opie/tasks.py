import logging
import threading
import os
import tempfile

import httpx
from celery import shared_task
from django.conf import settings
from django.utils import timezone  # Added for timezone.now()
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


@shared_task
def delete_vault_embeddings_task(project_id: str, file_id: int):
    """
    Delete embeddings for a vault file from PGVector
    """
    if not hasattr(settings, "LLAMAINDEX_INGESTION_URL") or not settings.LLAMAINDEX_INGESTION_URL:
        logger.error("LLAMAINDEX_INGESTION_URL is not configured")
        return
        
    service_url = settings.LLAMAINDEX_INGESTION_URL.rstrip("/")
    endpoint = f"{service_url}/delete-vault-embeddings"
    
    payload = {
        "project_id": project_id,
        "file_id": file_id,
        "table_name": "vault_vector_table",
        "schema_name": "ai"
    }
    
    api_key = settings.SYSTEM_API_KEY
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Successfully deleted vault embeddings for file {file_id} in project {project_id}")
    except Exception as e:
        logger.error(f"Failed to delete vault embeddings: {e}")


@shared_task
def delete_vectors_from_llamaindex_task(vector_table_name: str, file_uuid: str):
    """
    Asynchronously calls the LlamaIndex service to delete vectors
    associated with a specific file_uuid from a given vector_table_name.
    """
    if not hasattr(settings, "LLAMAINDEX_INGESTION_URL") or not settings.LLAMAINDEX_INGESTION_URL:
        logger.error("LLAMAINDEX_INGESTION_URL is not configured in Django settings. Cannot delete vectors.")
        return

    if not hasattr(settings, "SYSTEM_API_KEY") or not settings.SYSTEM_API_KEY:
        logger.error(
            "SYSTEM_API_KEY is not configured in Django settings. Cannot call LlamaIndex service."
        )
        return

    service_url = settings.LLAMAINDEX_INGESTION_URL.rstrip("/")
    endpoint = f"{service_url}/delete-vectors"

    payload = {"vector_table_name": vector_table_name, "file_uuid": file_uuid}

    api_key = settings.SYSTEM_API_KEY
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
    from .models import FileKnowledgeBaseLink, VaultFile

    """
    Triggers the ingestion of a single file by making an HTTP POST request to the Cloud Run service.
    Handles FileKnowledgeBaseLink and VaultFile status updates based on the outcome.
    """

    print("file_info", file_info.get("embedding_provider"))
    print("file_info--------------------------------------------------->", file_info)
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

    # Check if this is a vault file
    is_vault_file = custom_metadata and custom_metadata.get("vault_file", False)
    vault_file_id = custom_metadata.get("vault_file_id") if custom_metadata else None

    print("is_vault_file=================>")
    print(is_vault_file)
    
    print("vault_file_id=================>")
    print(vault_file_id)

    print("file_uuid=================>")
    print(file_uuid)

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

    # Validate required fields
    required_fields = {
        "file_path": gcs_path,
        "vector_table_name": vector_table_name,
        "file_uuid": file_uuid,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "user_uuid": user_uuid,
    }

    for field_name, value in required_fields.items():
        if value is None:
            error_msg = f"Required field '{field_name}' is None"
            logger.error(error_msg)
            if link_id:
                FileKnowledgeBaseLink.objects.filter(id=link_id).update(
                    ingestion_status="failed",
                    ingestion_error=error_msg
                )
            raise ValueError(error_msg)

    payload = {
        "file_path": gcs_path,
        "vector_table_name": vector_table_name,
        "file_uuid": str(file_uuid),
        "link_id": str(link_id) if link_id is not None else None,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "user_uuid": str(user_uuid),
        "team_id": str(team_id) if team_id is not None else None,
        "knowledgebase_id": str(knowledgebase_id) if knowledgebase_id is not None else None,
        "project_id": str(project_id) if project_id is not None else None,
        "custom_metadata": custom_metadata,
    }

    print(f"Payload: {payload}")

    api_key = getattr(settings, "SYSTEM_API_KEY", None)
    if not api_key:
        logger.error("SYSTEM_API_KEY is not configured. Cannot authenticate with ingestion service.")
        raise ValueError("SYSTEM_API_KEY not configured.")

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Request-Source": "opie-celery-ingestion",  # To identify the source of the request
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

        # Update vault file status if this is a vault file
        if is_vault_file and vault_file_id:
            try:
                VaultFile.objects.filter(id=vault_file_id).update(
                    embedding_status="processing",
                    embedding_error=None,
                )
                logger.info(f"Updated vault file {vault_file_id} status to processing")
            except Exception as e:
                logger.error(f"Failed to update vault file {vault_file_id} status: {e}")

        def fire_and_forget_ingestion(ingestion_url, payload, headers, is_vault_file, vault_file_id):
            try:
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(ingestion_url, json=payload, headers=headers)

                    # Log the response details before raising for status
                    logger.info(f"Ingestion response status: {response.status_code}")
                    if response.status_code != 200:
                        logger.error(f"Ingestion failed with status {response.status_code}: {response.text}")

                    response.raise_for_status()

                    # For vault files, update completion status after successful ingestion
                    if is_vault_file and vault_file_id:
                        try:
                            VaultFile.objects.filter(id=vault_file_id).update(
                                embedding_status="completed",
                                is_embedded=True,
                                embedded_at=timezone.now(),
                                embedding_error=None,
                            )
                            logger.info(f"✅ Vault file {vault_file_id} embedding completed")
                        except Exception as e:
                            logger.error(f"Failed to update vault file {vault_file_id} completion: {e}")
            except Exception as e:
                logger.error(f"Fire and forget ingestion failed: {e}")
                # For vault files, update failure status
                if is_vault_file and vault_file_id:
                    try:
                        VaultFile.objects.filter(id=vault_file_id).update(
                            embedding_status="failed",
                            embedding_error=f"Ingestion failed: {str(e)[:150]}",
                        )
                    except Exception as db_e:
                        logger.error(f"Failed to update vault file status to failed: {db_e}")
                raise

        thread = threading.Thread(target=fire_and_forget_ingestion, args=(ingestion_url, payload, headers, is_vault_file, vault_file_id), daemon=True)
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

        # Update vault file status if this is a vault file
        if is_vault_file and vault_file_id:
            try:
                VaultFile.objects.filter(id=vault_file_id).update(
                    embedding_status="failed",
                    embedding_error=error_message_for_db,
                )
                logger.info(f"Updated vault file {vault_file_id} status to failed")
            except Exception as db_e:
                logger.error(f"Failed to update vault file {vault_file_id} to failed: {db_e}")
        # Re-raise the exception. Celery's autoretry_for=(Exception,) will handle retrying it
        # based on the retry_kwargs (max_retries, countdown).
        # If max_retries is exhausted, Celery marks the task as failed.
        raise


import json
import redis
from contextlib import contextmanager
from django.db import connection

@contextmanager
def pg_advisory_lock(lock_id: int):
    """A context manager for PostgreSQL advisory locks."""
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
        logger.info(f"Acquired advisory lock for ID: {lock_id}")
        yield True
    finally:
        if cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
            logger.info(f"Released advisory lock for ID: {lock_id}")
            cursor.close()


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3, "countdown": 60})
def embed_vault_file_task(self, vault_file_id):
    """
    Celery task to embed a vault file using KB ingestion infrastructure directly
    """
    from .models import VaultFile, VaultIngestionTask

    try:
        vault_file = VaultFile.objects.get(id=vault_file_id)
        logger.info(f"🔄 Creating ingestion task for vault file {vault_file.id}: {vault_file.original_filename}")

        # Create a new ingestion task
        ingestion_task = VaultIngestionTask.objects.create(
            vault_file=vault_file,
            celery_task_id=self.request.id,
        )

        # Set vault file status
        vault_file.embedding_status = "queued"
        vault_file.save(update_fields=["embedding_status"])

        # Trigger the processing task
        process_vault_ingestion.delay(ingestion_task.id)

        logger.info(f"✅ Vault file {vault_file.id} queued for ingestion with task {ingestion_task.id}")
        return {"success": True, "file_id": vault_file.id, "task_id": str(ingestion_task.id)}

    except VaultFile.DoesNotExist:
        logger.error(f"❌ VaultFile with ID {vault_file_id} not found")
        raise
    except Exception as e:
        logger.error(f"❌ Failed to create embedding task for vault file {vault_file_id}: {e}", exc_info=True)
        # Optionally update vault file status to failed here if it's critical
        try:
            VaultFile.objects.filter(id=vault_file_id).update(
                embedding_status="failed",
                embedding_error=f"Failed to create task: {str(e)[:150]}"
            )
        except Exception:
            pass # Ignore if vault file doesn't exist
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 5, "countdown": 60})
def process_vault_ingestion(self, task_id):
    """
    Processes a VaultIngestionTask by calling the Cloud Run service and streaming the response.
    """
    from .models import VaultFile, VaultIngestionTask

    try:
        task = VaultIngestionTask.objects.select_related('vault_file', 'vault_file__project').get(id=task_id)
    except VaultIngestionTask.DoesNotExist:
        logger.error(f"VaultIngestionTask with ID {task_id} not found. Aborting.")
        return

    # Use a hash of the vault file ID for the advisory lock
    lock_id = hash(f"vault_file_{task.vault_file.id}")

    with pg_advisory_lock(lock_id):
        # Re-fetch task to ensure we have the latest status after acquiring the lock
        task.refresh_from_db()

        # Update task status to processing
        task.status = "processing"
        task.started_at = timezone.now()
        task.attempt_count = self.request.retries + 1
        task.celery_task_id = self.request.id
        task.save()

        task.vault_file.embedding_status = "processing"
        task.vault_file.save(update_fields=["embedding_status"])

        redis_client = redis.from_url(settings.REDIS_URL)
        stream_key = f"ingest:events:vault:{task.id}"

        try:
            ingestion_base_url = getattr(settings, "LLAMAINDEX_INGESTION_URL", None)
            if not ingestion_base_url:
                raise ValueError("LLAMAINDEX_INGESTION_URL is not configured.")

            ingestion_url = f"{ingestion_base_url.rstrip('/')}/ingest-file"
            api_key = getattr(settings, "SYSTEM_API_KEY", None)
            if not api_key:
                raise ValueError("SYSTEM_API_KEY is not configured.")

            headers = {
                "Authorization": f"Api-Key {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/x-ndjson",
                "Idempotency-Key": str(task.idempotency_key),
            }

            # Determine file path - use Docker container path in development, GCS path in production
            if settings.DEBUG and hasattr(settings, 'MEDIA_ROOT'):
                # Development mode: use Docker container path for mounted volume
                file_path = f"/app/media/{task.vault_file.file.name}"
            else:
                # Production mode: use GCS path
                file_path = task.vault_file.file.name

            payload = {
                "file_path": file_path,
                "vector_table_name": getattr(settings, "VAULT_PGVECTOR_TABLE", "vault_vector_table"),
                "file_uuid": str(task.vault_file.id),
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-small",
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "user_uuid": str(task.vault_file.uploaded_by.uuid) if task.vault_file.uploaded_by else None,
                "project_id": str(task.vault_file.project.uuid) if task.vault_file.project else None,
                "custom_metadata": {
                    "vault_file": True,
                    "original_filename": task.vault_file.original_filename,
                    "file_type": task.vault_file.type,
                    "file_size": task.vault_file.size,
                    "vault_file_id": task.vault_file.id,
                }
            }

            final_status = "failed"
            with httpx.stream("POST", ingestion_url, json=payload, headers=headers, timeout=3600.0) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        progress_data = json.loads(line)
                        task.stage = progress_data.get("stage")
                        task.percent_complete = progress_data.get("percent")
                        task.save(update_fields=["stage", "percent_complete"])

                        # Publish event to Redis Stream
                        redis_client.xadd(stream_key, progress_data)

                        final_status = progress_data.get("status")

            if final_status == "completed":
                task.status = "completed"
                task.vault_file.embedding_status = "completed"
                task.vault_file.is_embedded = True
                task.vault_file.embedded_at = timezone.now()
            else:
                 raise ValueError("Ingestion stream ended without a 'completed' status.")

        except Exception as e:
            logger.error(f"Ingestion failed for task {task.id}: {e}", exc_info=True)
            task.status = "failed"
            task.last_error = str(e)
            task.vault_file.embedding_status = "failed"
            task.vault_file.embedding_error = str(e)
            raise # Re-raise to trigger Celery's retry mechanism

        finally:
            task.completed_at = timezone.now()
            task.save()
            task.vault_file.save()
            logger.info(f"Ingestion task {task.id} finished with status: {task.status}")
