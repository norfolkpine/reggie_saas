# Multi-Cloud Deployment Guide

This guide shows how to deploy your application to different cloud providers using SSH keys and GitHub Actions.

## Supported Cloud Providers

- ✅ **Google Cloud Platform** (GCP)
- ✅ **Amazon Web Services** (AWS)
- ✅ **Hetzner Cloud**
- ✅ **DigitalOcean**
- ✅ **Linode**
- ✅ **Any VPS provider with SSH access**

## Setup Process

### 1. Infrastructure Setup

#### Google Cloud Platform
```bash
# Deploy infrastructure with Terraform
cd infra/envs/prod
terraform init
terraform apply

# Generate deployment configuration
./deploy/generate-deployment-env.sh

# Setup SSH keys and VM
./deploy/check-vm-status.sh
```

#### AWS EC2
```bash
# Create EC2 instance manually or with Terraform
# Ensure security group allows SSH (port 22) and HTTP/HTTPS (ports 80, 443)

# Install Docker and Docker Compose
ssh ubuntu@your-ec2-ip << 'EOF'
  sudo apt-get update
  sudo apt-get install -y docker.io docker-compose
  sudo usermod -aG docker ubuntu
  sudo systemctl enable docker
  sudo systemctl start docker
EOF

# Generate SSH keys
./deploy/check-vm-status.sh
```

#### Hetzner Cloud
```bash
# Create Hetzner server manually or with Terraform
# Ensure firewall allows SSH (port 22) and HTTP/HTTPS (ports 80, 443)

# Install Docker and Docker Compose
ssh root@your-hetzner-ip << 'EOF'
  apt-get update
  apt-get install -y docker.io docker-compose
  systemctl enable docker
  systemctl start docker
EOF

# Generate SSH keys
./deploy/check-vm-status.sh
```

### 2. GitHub Actions Setup

1. **Add repository secrets:**
   - `VM_SSH_KEY` - Private SSH key (from `~/.ssh/github_actions_deploy`)
   - `VM_HOST` - Server IP address
   - `VM_USER` - SSH username (usually `ubuntu`, `root`, or `admin`)

2. **Configure workflow:**
   - The workflow in `.github/workflows/deploy-multi-cloud.yml` will automatically deploy
   - It works with any cloud provider that supports SSH

### 3. Cloud-Specific Considerations

#### Google Cloud Platform
- ✅ **Terraform support** - Full infrastructure as code
- ✅ **Automatic SSH key management** - Keys added to VM metadata
- ✅ **Docker pre-installed** - Via startup script

#### AWS EC2
- ⚠️ **Manual setup** - Create EC2 instance and security groups
- ⚠️ **Manual SSH key setup** - Add public key to `~/.ssh/authorized_keys`
- ⚠️ **Manual Docker install** - Install Docker and Docker Compose

#### Hetzner Cloud
- ⚠️ **Manual setup** - Create server and configure firewall
- ⚠️ **Manual SSH key setup** - Add public key to `~/.ssh/authorized_keys`
- ⚠️ **Manual Docker install** - Install Docker and Docker Compose

## Security Best Practices

### SSH Key Management
- ✅ **Use ED25519 keys** - More secure than RSA
- ✅ **Rotate keys regularly** - Generate new keys periodically
- ✅ **Use passphrase-protected keys** - For local development
- ✅ **No passphrase for CI/CD** - Automated deployments

### Network Security
- ✅ **Restrict SSH access** - Use security groups/firewalls
- ✅ **Use non-standard SSH ports** - Change from port 22
- ✅ **Enable fail2ban** - Protect against brute force attacks
- ✅ **Use VPN** - For additional security layer

### Application Security
- ✅ **Use HTTPS** - SSL/TLS certificates
- ✅ **Environment variables** - Store secrets securely
- ✅ **Regular updates** - Keep system and dependencies updated
- ✅ **Monitoring** - Log and monitor application health

## Troubleshooting

### Common Issues

1. **SSH connection failed**
   - Check security group/firewall rules
   - Verify SSH key is correct
   - Ensure server is running

2. **Docker permission denied**
   - Add user to docker group: `sudo usermod -aG docker $USER`
   - Restart session or reboot

3. **Application not starting**
   - Check Docker Compose logs: `docker-compose logs`
   - Verify environment variables
   - Check port availability

### Debug Commands

```bash
# Test SSH connection
ssh -i ~/.ssh/github_actions_deploy user@server-ip

# Check Docker status
ssh user@server-ip "docker ps"

# View application logs
ssh user@server-ip "docker-compose logs -f"

# Check system resources
ssh user@server-ip "df -h && free -h"
```

## Cost Optimization

### Google Cloud Platform
- Use preemptible instances for development
- Enable auto-scaling
- Use committed use discounts

### AWS
- Use Spot instances for development
- Enable auto-scaling
- Use Reserved instances for production

### Hetzner Cloud
- Use smaller instance types
- Monitor resource usage
- Scale up/down as needed

## Monitoring and Logging

### Application Monitoring
- Use Docker health checks
- Monitor resource usage
- Set up alerts for failures

### Log Management
- Centralize logs with ELK stack
- Use structured logging
- Implement log rotation

### Backup Strategy
- Regular database backups
- Application code in Git
- Configuration in version control
