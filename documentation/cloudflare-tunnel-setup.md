# Cloudflare Tunnel Setup for Production

This guide covers setting up Cloudflare tunnels for secure access to your Django application running on a private GCP VM.

## Overview

Cloudflare tunnels provide secure access to your private infrastructure without exposing public IPs or opening firewall ports. The `cloudflared` daemon runs on your VM and creates an outbound connection to Cloudflare, routing traffic through their network.

## Prerequisites

- GCP VM with private IP (configured via Terraform)
- IAP access to the VM (configured via Terraform)
- Cloudflare account with a domain
- Domain DNS managed by Cloudflare

## Architecture

```
Internet → Cloudflare → cloudflared daemon → Django app (localhost:8000)
```

- **No public IPs required**
- **No firewall ports opened**
- **Outbound connection only**
- **End-to-end encryption**

## Step 1: Deploy Infrastructure

Ensure your Terraform configuration is deployed with private networking:

```bash
cd terraform/environments/prod
terraform apply
```

This creates:
- VPC network with private subnet
- VM with private IP only
- IAP access for admin SSH
- CloudSQL with private IP

## Step 2: Access VM via IAP

SSH to your VM using Google Cloud IAP:

```bash
gcloud compute ssh opie-stack-vm \
  --zone=australia-southeast1-a \
  --project=bh-opie \
  --tunnel-through-iap
```

## Step 3: Install cloudflared

On the VM, install the Cloudflare tunnel daemon:

```bash
# Download latest cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

# Install cloudflared
sudo dpkg -i cloudflared-linux-amd64.deb

# Verify installation
cloudflared --version
```

## Step 4: Authenticate with Cloudflare

```bash
# Login to Cloudflare (opens browser)
cloudflared tunnel login
```

This will:
- Open your browser to Cloudflare
- Ask you to select the domain
- Download a certificate to `~/.cloudflared/cert.pem`

## Step 5: Create Tunnel

```bash
# Create a new tunnel
cloudflared tunnel create my-tunnel

# This creates a tunnel and saves credentials
# Note the tunnel ID for configuration
```

## Step 6: Configure Tunnel

Create the tunnel configuration file:

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

Add the following configuration:

```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: /etc/cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: yourdomain.com
    service: http://localhost:8000
  - hostname: api.yourdomain.com
    service: http://localhost:8000/api/
  - service: http_status:404
```

Replace:
- `YOUR_TUNNEL_ID` with the actual tunnel ID
- `yourdomain.com` with your domain
- `localhost:8000` with your Django app port

## Step 7: Configure DNS

Add DNS records for your tunnel:

```bash
# Add CNAME record for your domain
cloudflared tunnel route dns my-tunnel yourdomain.com

# Add CNAME record for API subdomain
cloudflared tunnel route dns my-tunnel api.yourdomain.com
```

## Step 8: Install as System Service

Create a systemd service for cloudflared:

```bash
sudo cloudflared service install
```

This creates:
- Service file: `/etc/systemd/system/cloudflared.service`
- Configuration: `/etc/cloudflared/config.yml`
- Credentials: `/etc/cloudflared/YOUR_TUNNEL_ID.json`

## Step 9: Start and Enable Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Start cloudflared service
sudo systemctl start cloudflared

# Enable to start on boot
sudo systemctl enable cloudflared

# Check status
sudo systemctl status cloudflared
```

## Step 10: Verify Setup

Check that the tunnel is working:

```bash
# Check tunnel status
cloudflared tunnel info my-tunnel

# Check service logs
sudo journalctl -u cloudflared -f

# Test connectivity
curl -H "Host: yourdomain.com" http://localhost:8000
```

## Security Benefits

### ✅ **Zero Attack Surface**
- No public IPs exposed
- No firewall ports opened
- No direct internet access to VM

### ✅ **Encrypted Traffic**
- End-to-end encryption via Cloudflare
- TLS termination at Cloudflare edge
- Secure tunnel to your application

### ✅ **Access Control**
- Cloudflare Access for additional auth
- IP allowlisting at Cloudflare level
- DDoS protection included

## Troubleshooting

### Tunnel Not Connecting
```bash
# Check cloudflared logs
sudo journalctl -u cloudflared -f

# Test tunnel manually
sudo cloudflared tunnel --config /etc/cloudflared/config.yml run my-tunnel
```

### DNS Issues
```bash
# Check DNS records
dig yourdomain.com
nslookup yourdomain.com

# Verify tunnel routes
cloudflared tunnel route list
```

### Application Not Responding
```bash
# Check if Django is running
sudo systemctl status your-django-app

# Test local connectivity
curl http://localhost:8000

# Check firewall (should be minimal)
sudo ufw status
```

## Monitoring

### Cloudflare Dashboard
- Monitor tunnel status
- View traffic metrics
- Check error rates

### Server Monitoring
```bash
# Check cloudflared service
sudo systemctl status cloudflared

# View logs
sudo journalctl -u cloudflared --since "1 hour ago"

# Monitor resources
htop
```

## Backup and Recovery

### Backup Configuration
```bash
# Backup tunnel config
sudo cp /etc/cloudflared/config.yml /backup/
sudo cp /etc/cloudflared/*.json /backup/
```

### Restore Configuration
```bash
# Restore from backup
sudo cp /backup/config.yml /etc/cloudflared/
sudo cp /backup/*.json /etc/cloudflared/
sudo systemctl restart cloudflared
```

## Advanced Configuration

### Multiple Domains
```yaml
ingress:
  - hostname: app.yourdomain.com
    service: http://localhost:8000
  - hostname: api.yourdomain.com
    service: http://localhost:8000/api/
  - hostname: admin.yourdomain.com
    service: http://localhost:8000/admin/
  - service: http_status:404
```

### Load Balancing
```yaml
ingress:
  - hostname: yourdomain.com
    service: http://localhost:8000
    originRequest:
      httpHostHeader: yourdomain.com
      noTLSVerify: true
```

### Custom Headers
```yaml
ingress:
  - hostname: yourdomain.com
    service: http://localhost:8000
    originRequest:
      httpHostHeader: yourdomain.com
      noTLSVerify: true
      originServerName: yourdomain.com
```

## Maintenance

### Update cloudflared
```bash
# Download latest version
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

# Install update
sudo dpkg -i cloudflared-linux-amd64.deb

# Restart service
sudo systemctl restart cloudflared
```

### Rotate Certificates
```bash
# Re-authenticate (if needed)
cloudflared tunnel login

# Restart service
sudo systemctl restart cloudflared
```

## Production Checklist

- [ ] Infrastructure deployed with private networking
- [ ] VM accessible via IAP
- [ ] cloudflared installed and configured
- [ ] DNS records created
- [ ] System service running
- [ ] Application responding through tunnel
- [ ] Monitoring configured
- [ ] Backup procedures in place
- [ ] Documentation updated

---

**Note**: This setup provides enterprise-grade security with zero public attack surface while maintaining full functionality through Cloudflare's global network.
