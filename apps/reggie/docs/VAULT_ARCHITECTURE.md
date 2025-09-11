# Vault Feature: System Architecture

This document outlines the high-level system architecture for the Vault feature, designed to provide a secure, scalable, and robust environment for managing and analyzing large volumes of sensitive documents.

## 1. Core Architectural Principles

The architecture is founded on the following principles:

-   **Security First:** The system is designed to meet the stringent confidentiality and compliance requirements of clients in regulated industries (legal, finance). Every architectural choice prioritizes data isolation and protection.
-   **Scalability:** The architecture must scale to support a large number of tenants (customers), each with a large number of documents, without a degradation in performance.
-   **Maintainability:** The system leverages existing technologies and patterns within the codebase to ensure it is straightforward to maintain, extend, and debug.

## 2. System Components

The architecture is composed of four main components that work together to handle the lifecycle of a document.

### 2.1. File Storage: Google Cloud Storage (GCS)

-   **What it is:** A highly durable and scalable object storage service.
-   **Why we use it:**
    -   **Scalability:** GCS can store petabytes of data, effectively providing unlimited storage for raw document files (PDFs, DOCX, etc.).
    -   **Decoupling:** It decouples the file storage from the application logic. The application only needs to store a reference (a URL/path) to the file, not the file itself.
    -   **Security:** GCS provides robust security features, including fine-grained permissions (IAM), and automatically encrypts all data at rest.

### 2.2. Metadata & Application Logic: PostgreSQL & Django

-   **What it is:** The primary relational database (PostgreSQL) managed by the Django application framework.
-   **Why we use it:**
    -   **Structured Data:** It is the source of truth for all structured metadata associated with a file, such as its name, owner, project, team permissions, and ingestion status.
    -   **Transactional Integrity:** PostgreSQL ensures that all changes to metadata are atomic and consistent.
    -   **Mature Ecosystem:** The Django ORM provides a secure and efficient way to interact with the database, reducing the risk of common vulnerabilities like SQL injection.

### 2.3. Asynchronous Processing: Celery

-   **What it is:** A distributed task queue for executing background tasks outside of the normal request-response cycle.
-   **Why we use it:**
    -   **Responsiveness:** Document processing (chunking, embedding) can be time-consuming. Offloading this work to a background task ensures the user interface remains fast and responsive. A user can upload a file and get an immediate confirmation, while the heavy lifting happens asynchronously.
    -   **Resilience & Retries:** Celery provides mechanisms to automatically retry failed tasks, making the ingestion pipeline more robust.
    -   **Scalability:** We can scale the number of Celery worker processes independently of the web application to handle higher ingestion loads.

### 2.4. Vector Storage & Search: pgvector

-   **What it is:** A PostgreSQL extension that enables the storage and efficient querying of vector embeddings.
-   **Why we use it:**
    -   **Integrated Solution:** It lives inside our existing PostgreSQL database, which simplifies the tech stack, reducing operational overhead and making backups and maintenance easier.
    -   **Powerful Indexing:** `pgvector` supports HNSW indexes, which allow for extremely fast and efficient similarity searches even over billions of vectors.
    -   **Combined Queries:** It allows us to combine traditional, exact-match metadata filtering (e.g., `WHERE team_id = '...'`) with vector similarity search in a single, atomic database query. This is the cornerstone of our security model.

## 3. Data Flow: Document Ingestion Lifecycle

1.  **Upload:** A user uploads a document via the application UI/API. The file is streamed directly to a secure, temporary location in GCS.
2.  **Metadata Creation:** A `File` record is created in the PostgreSQL database with the file's metadata and a pointer to its location in GCS.
3.  **Task Queuing:** A new ingestion task is dispatched to the Celery queue. The API responds to the user immediately that the file is "Processing".
4.  **Chunking & Embedding (Async):** A Celery worker picks up the task. It downloads the file from GCS, splits it into smaller text chunks, and uses an embedding model (e.g., from OpenAI) to convert each chunk into a vector embedding.
5.  **Vector Storage:** The worker stores each vector embedding in the `pgvector` table. Crucially, each vector is stored alongside a JSON object containing its associated metadata (`file_uuid`, `team_id`, `project_id`).
6.  **Status Update:** Upon successful completion, the worker updates the `File` record in the database to mark its status as "Completed".

## 4. Security & Compliance Model

### 4.1. Multi-Tenancy and Data Isolation

The system uses a **logically isolated, single-table multi-tenancy model**.

-   **Physical Storage:** All vectors for all tenants are stored in a single, partitioned PostgreSQL table.
-   **Logical Isolation:** Data is isolated through a **non-negotiable metadata filter** applied to every query. The application's data access layer will **always** inject a `WHERE` clause (e.g., `WHERE team_id = :current_team_id`) into every vector search query.
-   **Rationale:** This model provides the security of complete data separation with the manageability and performance benefits of a shared infrastructure. It is a standard, secure pattern for modern multi-tenant SaaS applications.

### 4.2. Supporting ISO 27001 Compliance

This architecture provides the technical foundation for an ISO 27001 certified environment by addressing the core principles of information security:

-   **Confidentiality:** Enforced through strict access controls, logical data isolation, and encryption.
-   **Integrity:** Maintained by the transactional nature of the PostgreSQL database and role-based access controls that prevent unauthorized modification of data.
-   **Availability:** Achieved by using highly-available, managed cloud services (GCS, Cloud SQL for PostgreSQL) with built-in redundancy and backup mechanisms.

### 4.3. Encryption

-   **Encryption in Transit:** All network traffic between the user, the application, and the database is secured with TLS.
-   **Encryption at Rest:** All files in GCS and all data in the PostgreSQL database are automatically encrypted at rest by the cloud provider.
