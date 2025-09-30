# Production Quick Reference

Quick reference guide for production deployment with private networking.

## 🚀 **Quick Start**

### 1. Deploy Infrastructure
```bash
cd terraform/environments/prod
terraform apply
```

### 2. Access VM via IAP
```bash
gcloud compute ssh opie-stack-vm \
  --zone=australia-southeast1-a \
  --project=bh-opie \
  --tunnel-through-iap
```

### 3. Set Up Cloudflare Tunnel
```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Login and create tunnel
cloudflared tunnel login
cloudflared tunnel create my-tunnel
```

## 🔧 **CI/CD Setup**

### GitHub Actions
- **Workflow**: `.github/workflows/deploy-production.yml`
- **Service Account**: `github-actions-production@bh-opie.iam.gserviceaccount.com`
- **Access Method**: IAP tunnel (no public IPs)

### Required GitHub Secrets
- `GCP_SA_KEY`: Service account key (base64 encoded)
- `SECRET_KEY`: Django secret key
- `DATABASE_URL`: Database connection string
- `DJANGO_DATABASE_HOST`: Database host
- `SYSTEM_API_KEY`: System API key

## 🔐 **Security Features**

- ✅ **Private IPs Only**: No public attack surface
- ✅ **IAP Access**: Identity-based VM access
- ✅ **Cloudflare Tunnels**: Secure web access
- ✅ **IAM Permissions**: Least privilege access
- ✅ **Audit Logging**: All access logged

## 📊 **Monitoring**

### Check VM Status
```bash
gcloud compute instances describe opie-stack-vm \
  --zone=australia-southeast1-a \
  --project=bh-opie
```

### Check CloudSQL Status
```bash
gcloud sql instances describe db0 --project=bh-opie
```

### View Logs
```bash
# VM logs
gcloud logging read "resource.type=gce_instance" --limit=50

# CloudSQL logs
gcloud logging read "resource.type=cloudsql_database" --limit=50
```

## 🛠️ **Troubleshooting**

### IAP Connection Issues
```bash
# Test IAP access
gcloud compute ssh opie-stack-vm \
  --zone=australia-southeast1-a \
  --project=bh-opie \
  --tunnel-through-iap \
  --command="echo 'Connection successful'"
```

### Cloudflare Tunnel Issues
```bash
# Check tunnel status
sudo systemctl status cloudflared

# View tunnel logs
sudo journalctl -u cloudflared -f
```

### Database Connection Issues
```bash
# Test database connection
gcloud sql connect db0 --user=postgres --database=postgres
```

## 📋 **Service Accounts**

| Service Account | Purpose | Key Roles |
|----------------|---------|-----------|
| `github-actions-production` | CI/CD | `iap.tunnelResourceAccessor`, `compute.instanceAdmin` |
| `vm-service-account` | VM operations | `cloudsql.client` |
| `cloud-run-test` | Cloud Run services | `storage.admin`, `cloudsql.client` |

## 🌐 **Network Architecture**

```
Internet → Cloudflare → cloudflared → Django App (localhost:8000)
                ↓
GitHub Actions → IAP → Private VM → CloudSQL (private IP)
```

## 📚 **Documentation Links**

- [Cloudflare Tunnel Setup](cloudflare-tunnel-setup.md)
- [CI/CD Production Setup](cicd-production-setup.md)
- [Deployment Checklist](deployment-checklist.md)
- [GCP Setup](gcp-setup.md)

## 🆘 **Emergency Contacts**

- **Infrastructure Issues**: Check GCP Console
- **Application Issues**: Check VM logs
- **Access Issues**: Verify IAM permissions
- **Network Issues**: Check Cloudflare dashboard

---

**Last Updated**: $(date)
**Environment**: Production
**Region**: australia-southeast1
