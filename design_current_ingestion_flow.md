# Current Document Ingestion Flow

This document outlines the existing architecture for the document ingestion process.

## Summary

The system uses a combination of a Django application with Celery and a separate Cloud Run service to handle document ingestion. The process is asynchronous from the user's perspective but involves a "fire-and-forget" pattern that has implications for reliability and status tracking.

## Step-by-Step Flow

1.  **Initiation**: The process begins in the main Django application when a Celery task, `ingest_single_file_via_http_task`, is called. This task is defined in `apps/opie/tasks.py`.

2.  **Dispatch**: The Celery task gathers all the necessary information about the file to be ingested (like its location in Google Cloud Storage). It then makes an HTTP POST request to a separate Cloud Run service. Critically, this is done in a "fire-and-forget" manner using a new thread, meaning the Celery task itself finishes immediately without waiting for a response from the Cloud Run service.

3.  **Execution**: The Cloud Run service, which is a FastAPI application defined in `cloudrun/bh-opie-llamaindex/main.py`, receives this request. The `/ingest-file` endpoint handles the entire ingestion process in a single, synchronous operation. This includes:
    *   Downloading the file from GCS.
    *   Chunking the document's content.
    *   Generating vector embeddings for each chunk.
    *   Storing the results in a PGVector database.

4.  **Status Updates**: While the Cloud Run service is processing the file, it sends separate HTTP requests back to the main Django application to update the ingestion progress in the database. This is how the system tracks the status of a long-running job that was initiated by a short-lived Celery task.

## Architecture Diagram

```
+------------------+      (2) Fire-and-forget HTTP POST
|                  |      /ingest-file
|  Django App      |------------------------------------->+-----------------+
|  (with Celery)   |                                      |                 |
|                  |      (4) Progress Update HTTP POST    |  Cloud Run      |
|  ingest_single_  |<-------------------------------------|  Service        |
|  file_via_http_  |      (e.g., /update-progress)         |  (FastAPI)      |
|  task            |                                      |                 |
+------------------+                                      +-------+---------+
       ^                                                           | (3) Synchronous
       | (1) Task triggered                                        | Ingestion
       |                                                           | (Download, Chunk,
+------+------+                                                    |  Embed, Store)
|             |                                                    |
| Celery      |                                                    v
| Worker      |                                             +------+------+
+-------------+                                             |             |
                                                            |  PGVector   |
                                                            |  Database   |
                                                            |             |
                                                            +-------------+
```

## Key Characteristics

*   **Loose Coupling**: The Django application is decoupled from the ingestion logic.
*   **"Fire-and-Forget"**: The Celery task does not wait for ingestion to complete, which can make error handling and status tracking complex.
*   **Synchronous Cloud Run Task**: The Cloud Run service performs a potentially long-running, synchronous task, which could be prone to timeouts with large files.
*   **Stateful Communication**: The Cloud Run service communicates progress back to the main application, making the overall process stateful despite the initial fire-and-forget call.