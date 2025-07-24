# Ben Heath SaaS Backend – Technical Documentation

## Table of Contents
1. Project Overview
2. Architecture
3. Key Components
4. RAG Ingestion Pipeline (Cloud Run)
5. Environment Variables & Configuration
6. Workflows
7. Dependencies
8. Developer Onboarding Guide
9. Testing & Quality
10. Appendix: Excluded Apps

---

## Project Overview

Ben Heath SaaS is a modular backend platform for blockchain analytics and knowledge management. It is built with Django and Python, providing robust APIs, user/team management, integrations, and a scalable architecture for AI-powered document retrieval and analytics.

- **Frontend**: Separate React repository (not included here).
- **Backend**: Django-based, with a microservice for RAG (Retrieval-Augmented Generation) ingestion deployed on Google Cloud Run.

---

## Architecture

**High-Level Diagram (textual):**

```
[React Frontend] <--REST/WS--> [Django Backend] <--API--> [Cloud Run RAG Service]
                                              |           |
                                              |           +--> [GCS, Google Drive, Web URLs, Dropbox, OpenAI, Postgres (pgvector)]
                                              |
                                              +--> [Celery/Redis, Stripe, Slack, etc.]
```

- **Django Backend**: Core business logic, user/team management, API endpoints, authentication, billing, and integrations.
- **Cloud Run Microservice**: Handles RAG ingestion—processing documents from Google Cloud Storage, Google Drive, web URLs, and Dropbox, embedding them with OpenAI, and storing vectors in PostgreSQL (pgvector).
- **Celery & Redis**: For background tasks and real-time features.
- **PostgreSQL**: Main relational database, with pgvector extension for vector search.
- **Google Cloud Platform**: Used for storage, secret management, and serverless compute (Cloud Run).

---

## Key Components

### Core Django Apps

- **reggie**: Core business logic, document and knowledge base management, ingestion, and agent orchestration.
- **users**: User management, authentication, and profile handling.
- **slack_integration**: Slack OAuth, bot integration, and storage.
- **app_integrations**: Integrations with third-party apps and services.
- **teams**: Team management, roles, permissions, and invitations.
- **support**: Support ticketing and user support workflows.
- **utils**: Shared utilities for billing, slugs, timezones, etc.
- **web**: Web-specific logic, context processors, and static/media storage backends.
- **api**: API schema, permissions, and helpers.
- **dashboard**: Dashboard views and services.
- **subscriptions**: Subscription management, webhooks, feature gating, and billing.
- **content**: Content and block management.
- **authentication**: Authentication endpoints and serializers.

### Excluded Apps

- `chat`, `ai_images`, `group_chat`, `teams_example`, `wagtail` (CMS)

---

## RAG Ingestion Pipeline (Cloud Run)

### Overview

The `cloudrun/` directory contains a FastAPI microservice for RAG ingestion, designed for scalable, serverless deployment on Google Cloud Run.

#### Workflow

1. **Document Ingestion**: Receives requests to ingest documents from a specified source, which can be:
   - Google Cloud Storage (GCS)
   - Google Drive
   - Web URLs
   - Dropbox
2. **Embedding**: Uses OpenAI's embedding API to vectorize document content.
3. **Vector Storage**: Stores embeddings in a PostgreSQL database with the pgvector extension.
4. **Progress Reporting**: Optionally reports progress back to the main Django API.

#### Key Endpoints

- `POST /ingest-gcs`: Ingests documents from GCS.
- `POST /ingest-drive`: Ingests documents from Google Drive.
- `POST /ingest-url`: Ingests documents from web URLs.
- `POST /ingest-dropbox`: Ingests documents from Dropbox.
- `POST /ingest-file`: Ingests a single file from any supported source.
- `GET /`: Health check.

#### Dependencies

- FastAPI, LlamaIndex, Google Cloud libraries, OpenAI, psycopg2, tqdm

#### Environment Variables

- `GOOGLE_APPLICATION_CREDENTIALS`
- `GCS_BUCKET`
- `POSTGRES_URL`
- `PGVECTOR_TABLE`
- `PGVECTOR_SCHEMA`
- `OPENAI_API_KEY`
- `GOOGLE_DRIVE_API_KEY`
- `DROPBOX_API_KEY`
- (and any other required for new sources)

See `cloudrun/bh-reggie-llamaindex-main/env.example` for a full list.

#### Deployment

- Automated via Cloud Build and Google Cloud Run.
- Uses Google Secret Manager for secure environment variable management.

---

## Environment Variables & Configuration

### Django Backend

Environment variables are loaded from `.env` or Google Secret Manager. Key variables include:

- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `DATABASE_URL`
- `REDIS_URL`
- `EMAIL_BACKEND`, `SERVER_EMAIL`, `DEFAULT_FROM_EMAIL`
- `STRIPE_LIVE_PUBLIC_KEY`, `STRIPE_LIVE_SECRET_KEY`, etc.
- `SLACK_BOT_TOKEN`, `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`
- `GCS_BUCKET`, `AWS_ACCESS_KEY_ID`, etc. (for storage)
- See `bh_reggie/settings.py` for the full list.

### Cloud Run RAG Service

See `cloudrun/bh-reggie-llamaindex-main/env.example` for required variables.

---

## Workflows

### User/Team Management

- Users can register, authenticate (including via Google), and join or create teams.
- Teams have roles, permissions, and can invite new members.

### Document Ingestion & Knowledge Base

- Documents are uploaded and parsed by agents.
- Knowledge bases are created per project, with metadata and unique IDs.
- RAG ingestion is triggered for new documents, handled by the Cloud Run service, supporting GCS, Google Drive, web URLs, and Dropbox.

### Integrations

- Slack: OAuth, bot messaging, and event handling.
- Stripe: Subscription and billing management.
- Other app integrations via `app_integrations`.

### Background Tasks

- Celery is used for asynchronous and scheduled tasks (e.g., notifications, ingestion, billing updates).

---

## Dependencies

### Backend

- Django, Django REST Framework, Celery, Redis, PostgreSQL (pgvector)
- Allauth, djstripe, drf_spectacular, django-waffle, etc.

### Cloud Run RAG Service

- FastAPI, LlamaIndex, Google Cloud libraries, OpenAI, psycopg2, tqdm

---

## Developer Onboarding Guide

1. **Clone the Repository**
   ```bash
   git clone <repo-url>
   cd <repo-directory>
   ```

2. **Set Up Python Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r dev-requirements.txt
   ```

3. **Configure Environment Variables**
   - Copy `.env.example` to `.env` and fill in required values.
   - For Cloud Run, see `cloudrun/bh-reggie-llamaindex-main/env.example`.

4. **Set Up Database**
   - Ensure PostgreSQL is running with the `pgvector` extension enabled.
   - Create the database:
     ```bash
     createdb bh_reggie
     ```
   - Run migrations:
     ```bash
     python manage.py migrate
     ```

5. **Run the Server**
   ```bash
   python manage.py runserver
   ```

6. **Run Celery (for background tasks)**
   ```bash
   celery -A bh_reggie worker -l INFO --pool=solo
   ```

7. **Run Tests**
   ```bash
   python manage.py test
   ```

8. **Cloud Run RAG Service (Local Dev)**
   ```bash
   cd cloudrun/bh-reggie-llamaindex-main
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8080
   ```

---

## Testing & Quality

- Use `python manage.py test` to run the test suite.
- Pre-commit hooks are configured for code quality.
- Linting and formatting are enforced via pre-commit and CI.

---

## Appendix: Excluded Apps

The following apps are present but not documented here per instructions:
- `chat`
- `ai_images`
- `group_chat`
- `teams_example`
- `wagtail` (CMS)

---
