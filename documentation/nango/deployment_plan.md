# Nango Integration Deployment Plan

This document outlines the steps to integrate Nango into the existing application deployment.

## 1. Update `docker-compose.prod.yml` to include Nango services

- Add a `nango-server` service using the official `nangohq/nango-server:hosted` image.
- Configure the `nango-server` to connect to the existing `cloudsql-proxy` for its database. This will require setting the database URL to point to a new `nango` database on the existing Cloud SQL instance.
- Add a `nango-redis` service for Nango's caching needs, keeping it separate from the main application's Redis to avoid conflicts.
- Ensure both new services are attached to the `app-network`.

## 2. Modify the GitHub Actions workflow to support Nango

- Update the `.github/workflows/deployment.yml` file.
- In the `Create deployment environment file on VM` step, add the necessary environment variables for the `nango-server`. This will include a `NANGO_ENCRYPTION_KEY`, database credentials, and server URLs.

## 3. Manual Setup

The following manual actions are required:

1.  Create a new database named `nango` in the existing Cloud SQL instance.
2.  Add a new secret named `NANGO_ENCRYPTION_KEY` to the GitHub environment for the deployment workflow.

## 4. Pre-commit steps

Complete pre-commit steps to make sure proper testing, verifications, reviews and reflections are done.

## 5. Submit the changes

Once the configuration is updated and verified, submit the changes with a descriptive commit message.
