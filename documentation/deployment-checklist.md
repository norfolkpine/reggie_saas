# Deployment Checklist: bh-reggie-test Stack

Use this checklist to ensure your GCP infrastructure and application deployment are complete and correct.

---

## 1. Cloud SQL (PostgreSQL)
- [ ] Cloud SQL instance (`db0`) created (Standard Edition, single-zone, PG15, db-f1-micro)
- [ ] Database (`bh_reggie_test`) created
- [ ] User (`reggieuser`) created with correct password
- [ ] `pgvector` extension enabled in the database

## 2. Service Accounts & IAM
- [ ] All required service accounts created (Cloud Run, GitHub Actions, Storage, SQL Backup)
- [ ] IAM roles assigned with least privilege
- [ ] Service account keys created only as needed

## 3. Storage Buckets
- [ ] GCS buckets created (static, media, docs, etc.)
- [ ] Bucket permissions set appropriately

## 4. Secrets Management
- [ ] All sensitive environment variables stored in Secret Manager
- [ ] Cloud Run service has access to required secrets

## 5. Application Configuration
- [ ] `.env` or config files updated with correct DB and GCP settings
- [ ] Application points to correct Cloud SQL instance, bucket, and secrets

## 6. Application Deployment
- [ ] Docker image built and pushed to Artifact Registry or GCR
- [ ] Application deployed to Cloud Run (or VM, if applicable)
- [ ] Environment variables/secrets injected at runtime

## 7. Verification
- [ ] Application connects successfully to Cloud SQL
- [ ] Vector search (pgvector) works if applicable
- [ ] All endpoints/services respond as expected

## 8. Cloudflare Tunnel Setup (Production)
- [ ] Infrastructure deployed with private networking
- [ ] VM accessible via IAP (Identity-Aware Proxy)
- [ ] cloudflared daemon installed on VM
- [ ] Cloudflare tunnel created and configured
- [ ] DNS records configured for tunnel
- [ ] System service running and enabled
- [ ] Application accessible through tunnel
- [ ] Monitoring and logging configured

## 9. (Optional) Additional Services
- [ ] y-provider integrated and deployed (if applicable)
- [ ] Docker Compose updated for local/dev multi-service setup

## 10. CI/CD Setup
- [ ] GitHub Actions workflow configured for private networking
- [ ] Service account created with IAP permissions
- [ ] GitHub secrets configured
- [ ] CI/CD pipeline tested
- [ ] Monitoring and alerting configured

## 11. Documentation
- [ ] All deployment steps and commands documented for team use
- [ ] Cloudflare tunnel setup documented
- [ ] CI/CD production setup documented
- [ ] README and checklist up to date

---

_Keep this checklist updated as your stack evolves!_
