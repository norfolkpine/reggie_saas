# === CONFIGURATION ===
PROJECT_ID=bh-opie
SERVICE_NAME=llamaindex-ingestion
REGION=australia-southeast1
SERVICE_ACCOUNT=cloud-run-test@bh-opie.iam.gserviceaccount.com
IMAGE=gcr.io/$(PROJECT_ID)/$(SERVICE_NAME)
GCS_BUCKET_NAME=bh-opie-media

# Load secret
SECRET_NAME = llamaindex-ingester-env
ENV_FILE = .env

# Upload .env file to Secret Manager
upload-env:
	gcloud secrets create $(SECRET_NAME) --project=$(PROJECT_ID) --replication-policy="automatic" || echo "Secret already exists"
	gcloud secrets versions add $(SECRET_NAME) --project=$(PROJECT_ID) --data-file=$(ENV_FILE)

# === BUILD, PUSH, DEPLOY ===

.PHONY: build push deploy update upload-env

default: build

# Build the Docker image
default: build

build:
	docker build -t $(IMAGE) .

# Push the Docker image to Google Container Registry
push:
	docker push $(IMAGE)

# Deploy to Cloud Run (creates or replaces the service)
deploy: push
	gcloud run deploy $(SERVICE_NAME) \
	  --image=$(IMAGE) \
	  --region=$(REGION) \
	  --platform=managed \
	  --service-account=$(SERVICE_ACCOUNT) \
	  --memory=2Gi \
	  --timeout=900 \
	  --allow-unauthenticated \
	  --set-env-vars=GCP_PROJECT=$(PROJECT_ID) \
	  --project=$(PROJECT_ID)

# Update Cloud Run service (no allow-unauthenticated by default)
update: push
	gcloud run deploy $(SERVICE_NAME) \
	  --image=$(IMAGE) \
	  --region=$(REGION) \
	  --platform=managed \
	  --service-account=$(SERVICE_ACCOUNT) \
	  --memory=2Gi \
	  --timeout=900 \
	  --set-env-vars=GCP_PROJECT=$(PROJECT_ID) \
	  --project=$(PROJECT_ID)

# Upload .env file to Secret Manager
upload-env:
	gcloud secrets create $(SECRET_NAME) --project=$(PROJECT_ID) --replication-policy="automatic" || echo "Secret already exists"
	gcloud secrets versions add $(SECRET_NAME) --project=$(PROJECT_ID) --data-file=$(ENV_FILE)

build:
	docker build -t $(IMAGE) .

auth:
	gcloud auth configure-docker gcr.io

push: auth
	docker push $(IMAGE)

# === DEPLOY ===
deploy-service: push
	gcloud run deploy $(SERVICE_NAME) \
	--image=$(IMAGE) \
	--region=$(REGION) \
	--platform=managed \
	--service-account=$(SERVICE_ACCOUNT) \
	--memory=2Gi \
	--timeout=900 \
	--allow-unauthenticated \
	--set-env-vars=GCP_PROJECT=$(PROJECT_ID)

update-service: push
	gcloud run deploy $(SERVICE_NAME) \
	--image=$(IMAGE) \
	--region=$(REGION) \
	--platform=managed \
	--service-account=$(SERVICE_ACCOUNT) \
	--memory=2Gi \
	--min-instances=0 \
	--max-instances=2 \
	--timeout=900 \
	--allow-unauthenticated \
	--set-env-vars=GCP_PROJECT=$(PROJECT_ID)

delete-service:
	gcloud run services delete $(SERVICE_NAME) --region=$(REGION)

# === CLOUD SCHEDULER TRIGGER (optional) ===

create-scheduler:
	gcloud scheduler jobs create http $(SERVICE_NAME)-trigger \
	--location=$(REGION) \
	--schedule="0 0 * * *" \
	--uri="https://$(REGION)-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$(PROJECT_ID)/services/$(SERVICE_NAME):invoke" \
	--http-method=POST \
	--oauth-service-account-email=$(SERVICE_ACCOUNT)

delete-scheduler:
	gcloud scheduler jobs delete $(SERVICE_NAME)-trigger --location=$(REGION)

# === BUCKET INFO ===

bucket-info:
	@echo "Fetching info for gs://$(GCS_BUCKET_NAME)..."
	@gsutil du -sh gs://$(GCS_BUCKET_NAME)
	@echo ""
	@echo "Total number of files:"
	@gsutil ls -r gs://$(GCS_BUCKET_NAME) | wc -l

# === LOCAL DEVELOPMENT ===

run-local:
	uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# === VIRTUAL ENVIRONMENT ===

VENV_DIR = .venv
PYTHON = python3

venv:
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "✅ Virtual environment created in $(VENV_DIR)"

activate:
	@echo "Run the following to activate virtual environment:"
	@echo "source $(VENV_DIR)/bin/activate"

install: venv
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install -r requirements.txt
	@echo "✅ Dependencies installed."

clean:
	rm -rf $(VENV_DIR)
	@echo "🧹 Virtual environment removed."

.PHONY: build auth push deploy-service update-service delete-service create-scheduler delete-scheduler run-local venv activate install clean bucket-info

setup-iam:
	gcloud projects add-iam-policy-binding $(PROJECT_ID) --member="serviceAccount:$(SERVICE_ACCOUNT)" --role="roles/secretmanager.secretAccessor"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) --member="serviceAccount:$(SERVICE_ACCOUNT)" --role="roles/storage.objectViewer"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) --member="serviceAccount:$(SERVICE_ACCOUNT)" --role="roles/cloudsql.client"
