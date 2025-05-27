# LlamaIndex GCS Ingestion Service

This service ingests documents from Google Cloud Storage (GCS), embeds them using OpenAI, and stores them into a Postgres Vector Store (PGVector).

Built with:
- FastAPI
- LlamaIndex
- Cloud Run (serverless deploy)
- Google Secret Manager for environment variables
- Automated CI/CD via Cloud Build

---

## ⚙️ Local Development Setup

1. **Clone the repo**

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

2. **Create virtual environment**

```bash
python3.12 -m venv llama_env
source llama_env/bin/activate
```

3. **Install dependencies**

With your virtual environment activated, install dependencies:

```bash
pip install -r requirements.txt
```

4. **Generate API Key**

---

## Deploying to Google Cloud Run (using Makefile)

You can deploy this service to Google Cloud Run using the provided Makefile. Before you start:
- Make sure you have the Google Cloud SDK (`gcloud`) installed and authenticated (`gcloud auth login`).
- Set the required variables in your environment or `.env`: `PROJECT_ID`, `SERVICE_ACCOUNT`, etc.

**Common deployment steps:**

```sh
# Build the container image
make build

# Authenticate with Google Cloud
make auth

# Push the image to Google Container Registry/Artifact Registry
make push

# Deploy the service to Cloud Run
make deploy-service
```

You can also update, delete, or manage the service using other Makefile targets. See the Makefile for all available commands and required variables.

---

The service needs an API key to communicate with the Django backend. From the Django project root:

```bash
python manage.py create_cloud_run_api_key
```

This will create a system user and generate an API key. Copy the generated key for the next step.

5. **Create `.env` file**

```dotenv
OPENAI_API_KEY=sk-...
GCS_BUCKET=your-gcs-bucket-name
POSTGRES_URL=postgresql://user:password@host:port/dbname
PGVECTOR_TABLE=your_vector_table
PGVECTOR_SCHEMA=public
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account.json
DJANGO_API_URL=http://localhost:8000/reggie
DJANGO_API_KEY=your-generated-api-key  # Add the key generated in step 4
```

6. **Run locally**

```bash
uvicorn main:app --reload --port 8080
```

App will start on `http://localhost:8080`.

---

## 🚀 Deployment to GCP

### 1. Build, Push and Deploy Manually

```bash
make upload-env   # upload .env to Secret Manager
make build
make push
make deploy-service
```

Or manually with GCP CLI:

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/llamaindex-ingestion
```

```bash
gcloud run deploy llamaindex-ingestion \
  --image gcr.io/YOUR_PROJECT_ID/llamaindex-ingestion \
  --platform managed \
  --region YOUR_REGION \
  --allow-unauthenticated \
  --set-env-vars GCS_BUCKET=...,POSTGRES_URL=...,PGVECTOR_TABLE=...,PGVECTOR_SCHEMA=...,OPENAI_API_KEY=...,GOOGLE_APPLICATION_CREDENTIALS=/tmp/creds/creds.json
```

### 2. Setup Google Secret Manager

```bash
gcloud secrets create llamaindex-ingester-env --replication-policy="automatic"
```

```bash
gcloud secrets versions add llamaindex-ingester-env --data-file=.env
```

### 3. CI/CD Automatic Deployments

- Push to `main` branch → Cloud Build triggers
- Cloud Build automatically:
  - Builds Docker image
  - Pushes to GCR
  - Deploys new revision to Cloud Run

No manual steps needed after push.

---

## 🛡️ GCP IAM Permissions Needed

Attach these roles to your Cloud Run Service Account:
- `roles/secretmanager.secretAccessor` (read secrets)
- `roles/storage.objectViewer` (read GCS files)
- `roles/cloudsql.client` (connect to CloudSQL, if used)

Command examples:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 📦 Project Structure

```
/app
  - main.py          # FastAPI app
Dockerfile           # Multi-stage build
Makefile             # Local dev + deploy automation
requirements.txt     # Dependencies
cloudbuild.yaml      # CI/CD config for Cloud Build
README.md            # You are here
```

---

## 📄 API Endpoints

| Method | URL | Description |
|:------|:----|:-------------|
| POST | `/ingest-gcs` | Ingest multiple documents from GCS prefix |
| POST | `/ingest-file` | Ingest a single file from GCS |
| GET  | `/` | Healthcheck |

**Example usage**

In Python:

```python
import requests

CLOUD_RUN_URL = "https://your-cloud-run-url/ingest-gcs"
payload = {
    "gcs_prefix": "global/library/",
    "file_limit": 1,
    "vector_table_name": "kb_customer_123"
}

res = requests.post(CLOUD_RUN_URL, json=payload)
print(res.json())
```

Full rebuild:

```python
requests.post("https://your-cloud-run-url/ingest-gcs", json={
    "gcs_prefix": "global/library/",
    "file_limit": 1000,
    "vector_table_name": "kb_customer_123"
})
```

Local testing:

```bash
curl -X POST http://localhost:8080/ingest-gcs \
  -H "Content-Type: application/json" \
  -d '{
    "gcs_prefix": "test/",
    "vector_table_name": "your-kb-id"
  }'
```

Or from Python:

```python
import requests

res = requests.post("http://localhost:8080/ingest-gcs", json={
    "gcs_prefix": "test/",
    "vector_table_name": "your-kb-id"
})
print(res.json())
```

Reference: [LlamaIndex Vector Store Integrations](https://docs.llamaindex.ai/en/stable/community/integrations/vector_stores/)

---

## 🧪 Running and Testing (Single File Ingest)

Run the server locally:

```bash
uvicorn main:app --reload --port 8080
```

Test ingestion with curl:

```bash
curl -X POST http://localhost:8080/ingest-file \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "test/file.pdf",
    "vector_table_name": "your-kb-id"
  }'
```

Or test ingestion from Python:

```python
import requests

res = requests.post("http://localhost:8080/ingest-file", json={
    "file_path": "test/file.pdf",
    "vector_table_name": "your-kb-id"
})
print(res.json())
```

Reference: [LlamaIndex Cloud SQL PG Example](https://github.com/googleapis/llama-index-cloud-sql-pg-python/blob/main/samples/llama_index_vector_store.ipynb)

https://medium.com/@abul.aala.fareh/customizing-documents-in-llamaindex-357de97d3917

---

## 📳 Notes

- In local development, environment loads from `.env`.
- In production (Cloud Run), environment loads from Secret Manager automatically.
- Use `lifespan` event handler (no deprecated `@on_event`).

---

# ✅ That's it.
Happy Ingesting 🚀

# Test curl
curl -X POST https://llamaindex-ingestion-776892553125.us-central1.run.app/ingest-gcs \
  -H "Content-Type: application/json" \
  -d '{
    "gcs_prefix": "reggie-data/global/library",
    "file_limit": 1,
    "vector_table_name": "pdf_documents"
  }'
