# Troubleshooting Guide V2

This guide helps you diagnose and fix common issues with the Reggie SaaS deployment.

## Table of Contents

1. [Cloud SQL Connection Issues](#cloud-sql-connection-issues)
2. [Docker and Container Issues](#docker-and-container-issues)
3. [GitHub Actions Deployment Issues](#github-actions-deployment-issues)
4. [Database Migration Issues](#database-migration-issues)
5. [Authentication and Permissions](#authentication-and-permissions)
6. [Network and Connectivity](#network-and-connectivity)
7. [GCS Document Storage Issues](#gcs-document-storage-issues)
8. [Performance Issues](#performance-issues)
9. [Log Analysis](#log-analysis)
10. [Emergency Recovery](#emergency-recovery)

## Cloud SQL Connection Issues

### Issue: "Connection refused" or "Server closed the connection"

**Symptoms:**
- `psql: error: connection to server at "localhost" (::1), port 5432 failed: server closed the connection unexpectedly`
- `django.db.utils.OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed`

**Diagnosis:**
```bash
# Check if Cloud SQL proxy is running
./scripts/cloudsql-proxy-with-temp-ip.sh --status

# Check Cloud SQL instance status
gcloud sql instances describe db0 --project=bh-opie

# Test database connection
./scripts/cloudsql-proxy-with-temp-ip.sh --test
```

**Solutions:**

1. **Cloud SQL Proxy Not Running:**
   ```bash
   # Start the proxy
   ./scripts/cloudsql-proxy-with-temp-ip.sh --start
   ```

2. **Cloud SQL Instance Not Accessible:**
   ```bash
   # Check if instance has public IP enabled
   gcloud sql instances describe db0 --project=bh-opie --format="value(ipAddresses[0].ipAddress)"
   
   # If no public IP, enable temporarily
   gcloud sql instances patch db0 --project=bh-opie --assign-ip --quiet
   ```

3. **Authentication Issues:**
   ```bash
   # Check service account credentials
   gcloud auth list
   
   # Re-authenticate if needed
   gcloud auth activate-service-account --key-file=.gcp/creds/bh-opie/cloud-run.json
   ```

### Issue: "Password authentication failed"

**Symptoms:**
- `psql: error: connection to server at "localhost" (::1), port 5432 failed: FATAL: password authentication failed for user "opieuser"`

**Solutions:**

1. **User Doesn't Exist:**
   ```bash
   # Create the database user
   bash deploy/3_gcp-create-cloudsql-pgvector.sh
   ```

2. **Wrong Password:**
   ```bash
   # Check password in deployment.env
   cat deployment.env | grep DB_PASS
   
   # Update password if needed
   gcloud sql users set-password opieuser --instance=db0 --password=NEW_PASSWORD --project=bh-opie
   ```

### Issue: "IAM authentication failed"

**Symptoms:**
- `cloud-sql-proxy: failed to connect to instance: Dial error: failed to dial`

**Solutions:**

1. **Service Account Permissions:**
   ```bash
   # Check service account has Cloud SQL Client role
   gcloud projects get-iam-policy bh-opie --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:cloud-run@bh-opie.iam.gserviceaccount.com"
   ```

2. **IAM Database User:**
   ```bash
   # Create IAM database user
   gcloud sql users create opieuser@bh-opie.iam.gserviceaccount.com --instance=db0 --type=cloud_iam_user --project=bh-opie
   ```

## Docker and Container Issues

### Issue: "Cannot connect to the Docker daemon"

**Symptoms:**
- `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`

**Solutions:**

1. **Docker Not Running:**
   ```bash
   # Start Docker service
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

2. **Permission Issues:**
   ```bash
   # Add user to docker group
   sudo usermod -aG docker $USER
   newgrp docker
   ```

### Issue: "Image not found" or "Pull access denied"

**Symptoms:**
- `Error response from daemon: pull access denied for australia-southeast1-docker.pkg.dev/bh-opie/containers/opie-web`

**Solutions:**

1. **Authentication:**
   ```bash
   # Authenticate with Artifact Registry
   gcloud auth configure-docker australia-southeast1-docker.pkg.dev
   ```

2. **Image Doesn't Exist:**
   ```bash
   # Check if image exists
   gcloud artifacts docker images list australia-southeast1-docker.pkg.dev/bh-opie/containers
   
   # Build and push if missing
   docker build -f Dockerfile.web -t australia-southeast1-docker.pkg.dev/bh-opie/containers/opie-web:latest .
   docker push australia-southeast1-docker.pkg.dev/bh-opie/containers/opie-web:latest
   ```

### Issue: "Port already in use"

**Symptoms:**
- `Error starting userland proxy: listen tcp 0.0.0.0:5432: bind: address already in use`

**Solutions:**

1. **Find Process Using Port:**
   ```bash
   # Find process using port 5432
   sudo lsof -i :5432
   
   # Kill the process
   sudo kill -9 <PID>
   ```

2. **Stop Conflicting Services:**
   ```bash
   # Stop local PostgreSQL if running
   sudo systemctl stop postgresql
   
   # Stop Cloud SQL proxy
   ./scripts/cloudsql-proxy-with-temp-ip.sh --stop
   ```

## GitHub Actions Deployment Issues

### Issue: "Permission denied" during SSH

**Symptoms:**
- `Permission denied (publickey)`

**Solutions:**

1. **Check SSH Key:**
   ```bash
   # Verify SSH key format
   echo "${{ secrets.VM_SSH_KEY }}" | base64 -d | head -1
   
   # Should start with "-----BEGIN OPENSSH PRIVATE KEY-----"
   ```

2. **Test SSH Connection:**
   ```bash
   # Test SSH manually
   ssh -i ~/.ssh/id_rsa ${{ secrets.VM_USER }}@${{ secrets.VM_HOST }}
   ```

### Issue: "Service account key not found"

**Symptoms:**
- `File not found: .gcp/creds/bh-opie/github-actions.json`

**Solutions:**

1. **Check File Exists:**
   ```bash
   # Verify file exists locally
   ls -la .gcp/creds/bh-opie/
   ```

2. **Upload Missing Files:**
   ```bash
   # Upload service account keys
   scp .gcp/creds/bh-opie/github-actions.json ${{ secrets.VM_USER }}@${{ secrets.VM_HOST }}:/home/github-actions/key.json
   ```

### Issue: "Terraform plan failed"

**Symptoms:**
- `Error: Error creating/updating instance`

**Solutions:**

1. **Check Quotas:**
   ```bash
   # Check GCP quotas
   gcloud compute project-info describe --project=bh-opie
   ```

2. **Verify Permissions:**
   ```bash
   # Check service account permissions
   gcloud projects get-iam-policy bh-opie --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:github-actions@bh-opie.iam.gserviceaccount.com"
   ```

## Database Migration Issues

### Issue: "Migration failed" or "Table already exists"

**Symptoms:**
- `django.db.utils.ProgrammingError: relation "table_name" already exists`

**Solutions:**

1. **Check Migration Status:**
   ```bash
   # Check applied migrations
   python manage.py showmigrations
   
   # Check database state
   python manage.py dbshell
   \dt  # List tables
   ```

2. **Reset Migrations:**
   ```bash
   # Fake unapply migrations
   python manage.py migrate app_name 0001 --fake
   
   # Reapply migrations
   python manage.py migrate
   ```

3. **Manual Database Fix:**
   ```bash
   # Connect to database
   psql -h 127.0.0.1 -p 5432 -U opieuser -d bh_opie
   
   # Check migration table
   SELECT * FROM django_migrations;
   
   # Fix if needed
   DELETE FROM django_migrations WHERE app='app_name' AND name='migration_name';
   ```

### Issue: "Vector extension not found"

**Symptoms:**
- `extension "vector" does not exist`

**Solutions:**

1. **Install pgvector:**
   ```bash
   # Connect to database
   psql -h 127.0.0.1 -p 5432 -U opieuser -d bh_opie
   
   # Create extension
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **Check Cloud SQL Configuration:**
   ```bash
   # Verify pgvector is enabled
   gcloud sql instances describe db0 --project=bh-opie --format="value(settings.databaseFlags[].name)"
   ```

## Authentication and Permissions

### Issue: "Insufficient permissions"

**Symptoms:**
- `The caller does not have permission`

**Solutions:**

1. **Check IAM Roles:**
   ```bash
   # List service account roles
   gcloud projects get-iam-policy bh-opie --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:service-account@bh-opie.iam.gserviceaccount.com"
   ```

2. **Grant Required Roles:**
   ```bash
   # Grant Cloud SQL Client role
   gcloud projects add-iam-policy-binding bh-opie --member="serviceAccount:service-account@bh-opie.iam.gserviceaccount.com" --role="roles/cloudsql.client"
   ```

### Issue: "Service account key invalid"

**Symptoms:**
- `Invalid key file format`

**Solutions:**

1. **Regenerate Key:**
   ```bash
   # Create new service account key
   gcloud iam service-accounts keys create new-key.json --iam-account=service-account@bh-opie.iam.gserviceaccount.com
   ```

2. **Update Secrets:**
   - Update GitHub repository secrets
   - Update local `.gcp/creds/` files

## Network and Connectivity

### Issue: "Connection timeout"

**Symptoms:**
- `dial tcp: i/o timeout`

**Solutions:**

1. **Check VPC Configuration:**
   ```bash
   # Verify VPC peering
   gcloud compute networks peerings list
   
   # Check firewall rules
   gcloud compute firewall-rules list --filter="name~cloudsql"
   ```

2. **Test Network Connectivity:**
   ```bash
   # Test from VM
   ping 10.190.0.3  # Cloud SQL private IP
   
   # Test from local machine
   telnet 127.0.0.1 5432
   ```

### Issue: "DNS resolution failed"

**Symptoms:**
- `Failed to resolve 'metadata.google.internal'`

**Solutions:**

1. **Check DNS Configuration:**
   ```bash
   # Test DNS resolution
   nslookup metadata.google.internal
   
   # Check /etc/hosts
   cat /etc/hosts
   ```

2. **Restart Network Services:**
   ```bash
   # Restart networking
   sudo systemctl restart networking
   ```

## GCS Document Storage Issues

### Issue: "Blob not found in bucket" error

**Symptoms:**
- Error message: `Error getting object: Blob user=<uuid>/year=<year>/month=<month>/day=<day>/<doc_id>/file not found in bucket bh-opie-docs`
- Documents cannot be accessed or loaded
- Users report missing document content

**Root Cause:**
The `Document.key_base` property was using `datetime.today()` instead of the document's creation date (`created_at`), causing path mismatches when accessing documents created on different dates. This was fixed in the codebase, but existing documents may still have files stored with the correct creation-date path.

**Diagnosis:**
Use the document checking script to verify file existence and location:

```bash
# Activate virtual environment
source venv/bin/activate

# Check a specific document file
python scripts/check_document_file.py "user=47adba46-1bec-4bb1-a664-27fb0b81c14b/year=2025/month=10/day=27/4d61aecb-0293-43a2-a54a-e67c6fd395cd/file"
```

The script will:
- Verify if the file exists in the GCS bucket
- Show file metadata (size, content type, creation time)
- Decode base64 content
- Extract readable text from Y.js binary format
- Display XML structure of the document

**Solutions:**

1. **Verify File Location:**
   ```bash
   # List files for a specific user
   gcloud storage ls gs://bh-opie-docs/user=<user-uuid>/ --recursive
   
   # Check if file exists at expected path
   gcloud storage ls "gs://bh-opie-docs/user=<user-uuid>/year=<year>/month=<month>/day=<day>/<doc_id>/file"
   ```

2. **Check Document Creation Date:**
   ```bash
   # Connect to database and check document created_at
   python manage.py shell
   ```
   ```python
   from apps.docs.models import Document
   doc = Document.objects.get(id='<doc-id>')
   print(f"Created at: {doc.created_at}")
   print(f"File key: {doc.file_key}")
   ```

3. **Use Document Check Script:**
   ```bash
   # The script automatically handles:
   # - Authentication (falls back to service account file)
   # - Base64 decoding
   # - Y.js binary format parsing
   # - Text extraction
   
   source venv/bin/activate
   python scripts/check_document_file.py "<file_key>"
   ```

**Script Usage Examples:**

```bash
# Basic usage
python scripts/check_document_file.py "user=<uuid>/year=2025/month=11/day=01/<doc-id>/file"

# With custom bucket
python scripts/check_document_file.py "<file_key>" "bh-opie-docs"

# Get file path from Django shell
python manage.py shell
```
```python
from apps.docs.models import Document
doc = Document.objects.get(id='<doc-id>')
print(doc.file_key)  # Use this output in the script
```

**What the Script Shows:**
- ✅ File existence status
- File size and metadata
- Base64 decoded content
- Extracted text from Y.js format
- XML structure of the document
- Any errors during processing

**Verification Steps:**
1. Identify the document ID from the error message
2. Get the document's `file_key` using Django shell
3. Run the check script with the file key
4. Verify the file exists at the expected location
5. If file is missing, check if it exists at a different date path (creation date vs. today's date)

**Note:** After the code fix, new documents will use the correct creation-date-based path. Existing documents with files stored correctly will continue to work. Only documents where the file was never uploaded or was uploaded to the wrong path will have issues.

### Issue: "Cannot read document content"

**Symptoms:**
- Document exists in database but content is empty
- Error when trying to access document content
- Base64 decode errors

**Solutions:**
1. **Check File in GCS:**
   ```bash
   # Use the document check script
   python scripts/check_document_file.py "<file_key>"
   ```

2. **Verify Content Format:**
   - The script will automatically detect and decode base64
   - It will extract text from Y.js binary format if present
   - Check for any decoding errors in the script output

3. **Re-upload Document (if needed):**
   ```python
   # In Django shell
   from apps.docs.models import Document
   doc = Document.objects.get(id='<doc-id>')
   # Set content and save to trigger re-upload
   doc.content = "<content>"
   doc.save()
   ```

## Performance Issues

### Issue: "Slow database queries"

**Symptoms:**
- High response times
- Database CPU usage high

**Solutions:**

1. **Check Query Performance:**
   ```bash
   # Connect to database
   psql -h 127.0.0.1 -p 5432 -U opieuser -d bh_opie
   
   # Check active queries
   SELECT * FROM pg_stat_activity WHERE state = 'active';
   
   # Check slow queries
   SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;
   ```

2. **Optimize Database:**
   ```bash
   # Analyze tables
   ANALYZE;
   
   # Reindex if needed
   REINDEX DATABASE bh_opie;
   ```

### Issue: "High memory usage"

**Symptoms:**
- Out of memory errors
- Slow application performance

**Solutions:**

1. **Check Memory Usage:**
   ```bash
   # Check system memory
   free -h
   
   # Check Docker memory usage
   docker stats
   ```

2. **Optimize Docker:**
   ```bash
   # Limit container memory
   docker run --memory=2g your-image
   
   # Clean up unused containers
   docker system prune -a
   ```

## Log Analysis

### Cloud SQL Proxy Logs

```bash
# Check proxy logs
./scripts/cloudsql-proxy-with-temp-ip.sh --status

# View detailed logs
docker logs reggie_saas-cloudsql-proxy-1
```

### Application Logs

```bash
# Check Django logs
docker logs reggie_saas-web-1

# Check system logs
sudo journalctl -u cloudsql-proxy -f
```

### GitHub Actions Logs

1. Go to GitHub repository
2. Click "Actions" tab
3. Select the failed workflow
4. Click on the failed job
5. Review step logs for errors

## Emergency Recovery

### Complete System Reset

```bash
# Stop all services
sudo docker-compose -f docker-compose.prod.yml down
./scripts/cloudsql-proxy-with-temp-ip.sh --stop

# Clean up
sudo docker system prune -a
sudo rm -rf /opt/cloudsql-proxy

# Restart from scratch
./scripts/cloudsql-proxy-with-temp-ip.sh --start
sudo docker-compose -f docker-compose.prod.yml up -d
```

### Database Recovery

```bash
# Backup current database
pg_dump -h 127.0.0.1 -p 5432 -U opieuser -d bh_opie > backup.sql

# Restore from backup
psql -h 127.0.0.1 -p 5432 -U opieuser -d bh_opie < backup.sql
```

### Rollback Deployment

```bash
# Rollback to previous Docker image
sudo docker-compose -f docker-compose.prod.yml down
sudo docker pull australia-southeast1-docker.pkg.dev/bh-opie/containers/opie-web:previous-tag
sudo docker-compose -f docker-compose.prod.yml up -d
```

## Getting Help

1. **Check Logs First:** Always start with log analysis
2. **Test Components:** Isolate the issue by testing each component
3. **Verify Configuration:** Check all configuration files and environment variables
4. **Check Documentation:** Refer to Installation_V2.md for setup steps
5. **Contact Support:** If issues persist, provide:
   - Error messages
   - Log files
   - Configuration details
   - Steps to reproduce

## Common Commands Reference

```bash
# Cloud SQL proxy management
./scripts/cloudsql-proxy-with-temp-ip.sh --start
./scripts/cloudsql-proxy-with-temp-ip.sh --stop
./scripts/cloudsql-proxy-with-temp-ip.sh --test
./scripts/cloudsql-proxy-with-temp-ip.sh --status

# Production VM management
./scripts/start-cloudsql-proxy-production.sh --start-iam
./scripts/install-cloudsql-proxy-service.sh --install
sudo systemctl status cloudsql-proxy

# Docker management
sudo docker-compose -f docker-compose.prod.yml up -d
sudo docker-compose -f docker-compose.prod.yml down
sudo docker logs <container-name>

# Database management
psql -h 127.0.0.1 -p 5432 -U opieuser -d bh_opie
python manage.py migrate
python manage.py showmigrations

# GCP management
gcloud sql instances describe db0 --project=bh-opie
gcloud auth list
gcloud projects get-iam-policy bh-opie

# GCS document troubleshooting
source venv/bin/activate
python scripts/check_document_file.py "<file_key>"
gcloud storage ls gs://bh-opie-docs/ --recursive
gcloud auth activate-service-account --key-file=.gcp/creds/bh-opie/storage.json
```
