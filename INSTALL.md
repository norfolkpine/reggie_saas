# Installation Guide

This document provides step-by-step instructions to set up and install the project.

## Prerequisites
- [ ] Docker (if using Docker)
- [ ] Python 3.x (if running Python services)
- [ ] Any other dependencies you use (will be updated as you run commands)

## Dependency Management

This project uses `pip-tools` to manage Python dependencies. The workflow is:

1. **Add packages to `requirements/requirements.in`** - This file contains the main packages without version pins
2. **Generate `requirements/requirements.txt`** - This file contains all dependencies with exact versions

### Adding New Packages

When adding new Python packages to the project:

1. Add the package name to `requirements/requirements.in`:
   ```sh
   echo "new-package-name" >> requirements/requirements.in
   ```

2. **IMPORTANT**: Regenerate `requirements/requirements.txt` using pip-compile:
   ```sh
   pip-compile requirements/requirements.in
   ```

3. Install the updated requirements:
   ```sh
   pip install -r requirements/requirements.txt
   ```

### Why This Matters

- The Dockerfile uses `requirements/requirements.txt` for installing dependencies
- If you only add packages to `requirements.in` without running `pip-compile`, the packages won't be installed in Docker containers
- Always run `pip-compile` after modifying `requirements.in` to ensure Docker builds include all dependencies

### Common Issues

- **Missing packages in Docker**: Usually means `requirements.txt` wasn't regenerated after adding packages to `requirements.in`
- **Version conflicts**: `pip-compile` resolves dependency conflicts automatically
- **Build failures**: Ensure `pip-tools` is installed: `pip install pip-tools`

## Installation Steps
1. Clone the repository:
   ```sh
   git clone <repository-url>
   cd opie_saas
   ```

2. Create and activate a Python virtual environment:
   ```sh
   python -m venv venv
   source venv/bin/activate
   ```
   This creates an isolated Python environment for the project.

3. Install required Python packages:
   ```sh
   pip install -r requirements/requirements.txt
   ```
   This installs all dependencies needed to run the project.

4. Start Redis and pgvector databases using Docker Compose:
   ```sh
   docker-compose -f docker-compose.db.yml up -d
   ```
   This command will start the Redis and pgvector services defined in `docker-compose.db.yml` in detached mode.

5. Apply Django migrations:
   ```sh
   python manage.py makemigrations
   python manage.py migrate
   ```
   These commands create and apply the necessary database migrations for your Django project. Make sure your virtual environment is activated and the database services are running before executing these commands.

6. Create a Cloud Run API key:
   ```sh
   python manage.py create_cloud_run_api_key
   ```
   This command will create (or update) the system user and API key for the Cloud Run ingestion service. The key will be printed in the output.

7. Add the API key to your Cloud Run environment:
   1. Copy the example environment file:
      ```sh
      cp cloudrun/bh-opie-llamaindex/env.example cloudrun/bh-opie-llamaindex/.env
      ```
   2. Open `cloudrun/bh-opie-llamaindex/.env` in your editor and add the following line:
      ```
      DJANGO_API_KEY=NaWraIYw.lGALJ6cMJIT2vuN9CkfdoTLX6L6KH8rQ
      ```
   This ensures your Cloud Run service has the correct API key for authentication.

8. Create a Django superuser:
   ```sh
   python manage.py createsuperuser
   ```
   This command will prompt you to enter a username, email address, and password for the Django admin user. Follow the prompts to complete superuser creation. This account will allow you to log in to the Django admin interface.

8. Load agent instructions, outputs, and model providers:
   ```sh
   python manage.py load_agent_instructions
   python manage.py load_agent_outputs
   python manage.py load_model_providers
   ```
   These commands will populate your database with the required agent instructions, output types, and model providers. Make sure you have created a superuser before running these commands, as some scripts may require an existing user with ID=1.

9. Load supported apps:
   ```sh
   python manage.py load_apps
   ```
   This command will load the supported integrations/apps into your system. Run this after the previous setup steps.

10. Start the Django development server:
    ```sh
    python manage.py runserver
    ```
    This will start the Django app locally at http://127.0.0.1:8000/. You can now access the application in your browser. Use this only for development and testing.

11. Configure the ingestor (llamaindex) environment file:
    1. Copy the example environment file:
       ```sh
       cp cloudrun/bh-opie-llamaindex/env.example cloudrun/bh-opie-llamaindex/.env
       ```
    2. Ensure you have a valid Google Cloud credentials file at `.gcp/creds/storage.json`.
    3. Edit `cloudrun/bh-opie-llamaindex/.env` and update the following variables:

    ```env
    # === GCP Credentials ===
    GOOGLE_APPLICATION_CREDENTIALS=.gcp/creds/storage.json
    GCS_BUCKET_NAME=bh-opie-media
    GCS_PREFIX=opie-data/global/library/

    # === PostgreSQL Connection ===
    # Build POSTGRES_URL using your Django database settings from the main .env:
    # postgresql://<user>:<password>@<host>:<port>/<db>
    POSTGRES_URL=postgresql://${DJANGO_DATABASE_USER}:${DJANGO_DATABASE_PASSWORD}@${DJANGO_DATABASE_HOST}:${DJANGO_DATABASE_PORT}/${DJANGO_DATABASE_NAME}
    PGVECTOR_SCHEMA=public

    # === OpenAI ===
    OPENAI_API_KEY=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

    # === Django API ===
    DJANGO_API_URL=http://localhost:8000
    DJANGO_API_KEY=your-django-api-key
    ```
    
    - Replace `your-django-api-key` and any other placeholder values as needed.
    - The vector table name is provided dynamically via the API request and does not need to be set in the .env file.
    - The `POSTGRES_URL` can be constructed from your main `.env` Django variables:
      ```env
      DJANGO_DATABASE_NAME=bh_opie
      DJANGO_DATABASE_USER=postgres
      DJANGO_DATABASE_PASSWORD=postgres
      DJANGO_DATABASE_HOST=localhost
      DJANGO_DATABASE_PORT=5432
      ```
      Example result:
      ```env
      POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/bh_opie
      ```
    - Make sure the `.gcp/creds/storage.json` file exists and is valid for your GCP environment.

12. Build the Docker image for the ingestor:
    First, change into the ingestor directory:
    ```sh
    cd cloudrun/bh-opie-llamaindex
    ```
    Then build the Docker image:
    ```sh
    docker build -t llamaindex-ingester .
    ```
    This will build a Docker image named `llamaindex-ingester` using your ingestor's code and dependencies.


## Configuring Document Ingestion Engine (llamaindex-ingester)

13. Run the ingestor Docker container:
    Make sure you are still in the `cloudrun/bh-opie-llamaindex` directory, then run:
    ```sh
    docker run --env-file .env \
      -v "$(pwd)/.gcp:/app/.gcp:ro" \
      -p 8080:8080 \
      llamaindex-ingester
    ```
    - `--env-file .env` loads environment variables from your `.env` file.
    - `-v "$(pwd)/.gcp:/app/.gcp:ro"` mounts your GCP credentials into the container.
    - `-p 8080:8080` exposes the API on port 8080.
    - `llamaindex-ingester` is the image you built in the previous step.

    The ingestor API will be available at http://localhost:8080.

---

**Note for Ingestion Development:**
If you want to run the ingestor locally for development (without Docker), you can use a Python virtual environment:

```sh
python3.12 -m venv llama_env
source llama_env/bin/activate
python main.py
```

This is useful for quick development and debugging cycles. Make sure your `.env` and credentials are set up as described above.


---

# (Add more steps below as you run additional commands)


---

_As you run setup and installation commands, this file will be updated to reflect the exact steps required for your environment._


## Configuring Collaborative Docs (opie-y-provider)

The opie-y-provider service enables real-time collaborative documents. It should be run alongside your database and Django app.

### 1. Configure Environment Variables
- Copy the example env file:
  ```sh
  cp opie-y-provider/env.example opie-y-provider/.env
  ```
- Ensure `Y_PROVIDER_API_KEY` and `COLLABORATION_SERVER_SECRET` in `opie-y-provider/.env` match the values in your Django `.env`.
- Adjust other variables as needed for your environment (e.g., backend URLs, ports).

Example `.env`:
```env
COLLABORATION_API_URL=http://localhost:4444/collaboration/api/
COLLABORATION_BACKEND_BASE_URL=http://localhost:8000
COLLABORATION_SERVER_ORIGIN=http://localhost:3000
COLLABORATION_SERVER_SECRET=my-secret
COLLABORATION_WS_URL=ws://localhost:4444/collaboration/ws/
Y_PROVIDER_API_KEY=my-secret
PORT=4444
COLLABORATION_LOGGING=true
```

### 2. Build and Run with Docker Compose
- Add y-provider as a service in your main `docker-compose` file, or use its own Compose file:
  ```sh
  docker compose -f opie-y-provider/docker-compose.yml up --build
  ```
  This will build and start the y-provider service on port 4444.

### 3. (Optional) Run Standalone with Docker
  ```sh
  cd opie-y-provider
  docker build -t y-provider .
  docker run --env-file .env -p 4444:4444 y-provider
  ```

### 4. (Optional) Local Development (Production Build)
  ```sh
  cd opie-y-provider
  yarn install
  yarn build
  yarn start
  ```

### 5. (Optional) Local Development (Hot Reload / Dev Mode)
  For active development with hot reloading, use:
  ```sh
  cd opie-y-provider
  yarn install
  yarn dev
  ```
  This will start the y-provider in development mode with hot reload enabled.


### 6. (Optional) Run Celery Worker
To enable background task processing and ensure the `/health/` endpoint passes, start a Celery worker:

```sh
celery -A bh_opie worker --loglevel=info
```


---

## Running All Core Services

Once your database is populated, start the following services in separate terminals (or use process manager/tmux):

### 1. Start the Database
If using Docker Compose:
```sh
docker compose -f docker-compose.db.yml up
```

### 2. Start Django (Web/API server)
```sh
python manage.py runserver
```

### 3. Start y-provider (Dev Mode)
```sh
cd opie-y-provider
yarn install
yarn dev
```

### 4. Start LlamaIndex
```sh
cd cloudrun/bh-opie-llamaindex
# Activate your venv if needed
uvicorn main:app --reload --port 8080
```

### 5. Start Celery Worker
```sh
celery -A bh_opie worker --loglevel=info
```

---

## Production deployment
### Deploying the Ingestor to Google Cloud Run (using Makefile)

You can deploy the ingestor service to Google Cloud Run using the provided Makefile in `cloudrun/bh-opie-llamaindex/`.

**Prerequisites:**
- Install the Google Cloud SDK (`gcloud`) and authenticate: `gcloud auth login`
- Set required variables in your environment or `.env` (e.g., `PROJECT_ID`, `SERVICE_ACCOUNT`)

**Deployment steps:**

```sh
# Change to the ingestor directory
cd cloudrun/bh-opie-llamaindex

# Build the container image
make build

# Authenticate with Google Cloud
make auth

# Push the image to Google Container Registry/Artifact Registry
make push

# Deploy the service to Cloud Run
make deploy-service
```

Other Makefile targets are available for updating, deleting, or managing the service. See the Makefile for all available commands and required variables.

---

## Dependency Management

This project uses `pip-tools` to manage Python dependencies. The workflow is:

1. **Add packages to `requirements/requirements.in`** - This file contains the main packages without version pins
2. **Generate `requirements/requirements.txt`** - This file contains all dependencies with exact versions

### Adding New Packages

When adding new Python packages to the project:

1. Add the package name to `requirements/requirements.in`:
   ```sh
   echo "new-package-name" >> requirements/requirements.in
   ```

2. **IMPORTANT**: Regenerate `requirements/requirements.txt` using pip-compile:
   ```sh
   pip-compile requirements/requirements.in
   ```

3. Install the updated requirements:
   ```sh
   pip install -r requirements/requirements.txt
   ```

### Why This Matters

- The Dockerfile uses `requirements/requirements.txt` for installing dependencies
- If you only add packages to `requirements.in` without running `pip-compile`, the packages won't be installed in Docker containers
- Always run `pip-compile` after modifying `requirements.in` to ensure Docker builds include all dependencies

### Common Issues

- **Missing packages in Docker**: Usually means `requirements.txt` wasn't regenerated after adding packages to `requirements.in`
- **Version conflicts**: `pip-compile` resolves dependency conflicts automatically
- **Build failures**: Ensure `pip-tools` is installed: `pip install pip-tools`
