# Archived Docker Files

This folder contains Docker files that are no longer used by the GitHub Actions deployment workflow.

## Archived Files

### Dockerfiles
- `Dockerfile` - Old main Dockerfile (replaced by `Dockerfile.web`)
- `Dockerfile.django` - Django-specific Dockerfile (not used in CI/CD)
- `Dockerfile_old` - Old y-provider Dockerfile (replaced by `opie-y-provider/Dockerfile`)

### Docker Compose Files
- `docker-compose-dev.yml` - Development environment (not used in CI/CD)
- `docker-compose.cloudsql-proxy.yml` - Cloud SQL proxy setup (not used in CI/CD)
- `docker-compose.reggie.yml` - Reggie service compose (not used in CI/CD)
- `docker-compose.opie.yml` - Opie service compose (not used in CI/CD)
- `docker-compose.db.yml` - Database service compose (not used in CI/CD)
- `docker-compose.yml` - Generic compose file (not used in CI/CD)

## Active Files

The following Docker files are still actively used:

### In Root Directory
- `Dockerfile.web` - Main web application Dockerfile (used by GitHub Actions)

### In opie-y-provider/
- `Dockerfile` - Y-provider service Dockerfile (used by GitHub Actions)

### In cloudrun/bh-opie-llamaindex/
- `Dockerfile` - Llamaindex service Dockerfile (used by Cloud Build)

### In frontend/
- `Dockerfile` - Frontend service Dockerfile (used by frontend deployment)

### Docker Compose
- `docker-compose.prod.yml` - Production environment (used by GitHub Actions)

## Archive Date
Archived on: Thu Oct  2 16:55:00 WITA 2025
