#!/bin/bash

# Script to verify VM service account permissions for Cloud SQL proxy and GCS
# Run this script on the VM to check if the service account has required permissions

set -e

PROJECT_ID="bh-opie"
VM_SA_EMAIL=""

echo "=== VM Service Account Permission Verification ==="
echo "Project: $PROJECT_ID"
echo ""

# Get VM service account email
echo "1. Getting VM service account email..."
VM_SA_EMAIL=$(curl -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email 2>/dev/null || echo "")
if [ -n "$VM_SA_EMAIL" ]; then
    echo "✅ VM Service Account: $VM_SA_EMAIL"
else
    echo "❌ Could not get VM service account email"
    exit 1
fi
echo ""

# Test basic authentication
echo "2. Testing gcloud authentication..."
if gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q '@'; then
    echo "✅ gcloud authentication is active"
    ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -1)
    echo "   Active account: $ACTIVE_ACCOUNT"
else
    echo "❌ No active gcloud authentication found"
fi
echo ""

# Test Cloud SQL permissions
echo "3. Testing Cloud SQL permissions..."
echo "   Testing Cloud SQL instances list access..."
if gcloud sql instances list --format='table(name,state)' 2>/dev/null | grep -q "db0"; then
    echo "✅ Can list Cloud SQL instances"
else
    echo "❌ Cannot list Cloud SQL instances"
fi

echo "   Testing Cloud SQL instance details..."
if gcloud sql instances describe db0 --format='value(name)' 2>/dev/null | grep -q "db0"; then
    echo "✅ Can access Cloud SQL instance details"
else
    echo "❌ Cannot access Cloud SQL instance details"
fi

echo "   Testing Cloud SQL connection name..."
CONNECTION_NAME=$(gcloud sql instances describe db0 --format='value(connectionName)' 2>/dev/null || echo "")
if [ -n "$CONNECTION_NAME" ]; then
    echo "✅ Connection name: $CONNECTION_NAME"
else
    echo "❌ Cannot get Cloud SQL connection name"
fi
echo ""

# Test Storage permissions
echo "4. Testing Storage permissions..."
echo "   Testing Storage buckets list access..."
if gcloud storage buckets list --format='table(name,location)' 2>/dev/null | grep -q "bh-opie"; then
    echo "✅ Can list Storage buckets"
else
    echo "❌ Cannot list Storage buckets"
fi

echo "   Testing specific bucket access..."
if gcloud storage ls gs://bh-opie-media/ 2>/dev/null | head -1 >/dev/null; then
    echo "✅ Can access bh-opie-media bucket"
else
    echo "❌ Cannot access bh-opie-media bucket"
fi

if gcloud storage ls gs://bh-opie-static/ 2>/dev/null | head -1 >/dev/null; then
    echo "✅ Can access bh-opie-static bucket"
else
    echo "❌ Cannot access bh-opie-static bucket"
fi
echo ""

# Test Artifact Registry permissions
echo "5. Testing Artifact Registry permissions..."
echo "   Testing Artifact Registry repositories list..."
if gcloud artifacts repositories list --location=australia-southeast1 --format='table(name,format)' 2>/dev/null | grep -q "containers"; then
    echo "✅ Can list Artifact Registry repositories"
else
    echo "❌ Cannot list Artifact Registry repositories"
fi

echo "   Testing Docker image pull..."
if docker pull australia-southeast1-docker.pkg.dev/bh-opie/containers/opie-web:latest >/dev/null 2>&1; then
    echo "✅ Can pull Docker images from Artifact Registry"
else
    echo "❌ Cannot pull Docker images from Artifact Registry"
fi
echo ""

# Test Secret Manager permissions
echo "6. Testing Secret Manager permissions..."
echo "   Testing Secret Manager list access..."
if gcloud secrets list --limit=1 --format='table(name,createTime)' 2>/dev/null | grep -q "llamaindex"; then
    echo "✅ Can list Secret Manager secrets"
else
    echo "❌ Cannot list Secret Manager secrets"
fi
echo ""

# Check IAM roles (if accessible)
echo "7. Checking IAM roles for VM service account..."
echo "   Note: This may not be accessible from VM service account itself"
if gcloud projects get-iam-policy $PROJECT_ID --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:$VM_SA_EMAIL" 2>/dev/null; then
    echo "✅ IAM roles accessible"
else
    echo "⚠️  IAM roles not accessible (this is normal for VM service accounts)"
    echo "   Required roles for VM service account:"
    echo "   - roles/cloudsql.client"
    echo "   - roles/cloudsql.instanceUser"
    echo "   - roles/storage.objectAdmin (for GCS buckets)"
    echo "   - roles/artifactregistry.reader (for Docker images)"
    echo "   - roles/secretmanager.secretAccessor (for secrets)"
fi
echo ""

# Test Cloud SQL proxy connection
echo "8. Testing Cloud SQL proxy connection..."
echo "   Starting Cloud SQL proxy test..."

# Create a temporary Cloud SQL proxy test
cat > /tmp/test-cloudsql-proxy.sh << 'EOF'
#!/bin/bash
set -e

echo "Starting Cloud SQL proxy test..."
PROXY_PID=""

# Function to cleanup
cleanup() {
    if [ -n "$PROXY_PID" ]; then
        echo "Stopping Cloud SQL proxy test..."
        kill $PROXY_PID 2>/dev/null || true
        wait $PROXY_PID 2>/dev/null || true
    fi
    rm -f /tmp/test-cloudsql-proxy.sh
}
trap cleanup EXIT

# Start Cloud SQL proxy in background
echo "Starting Cloud SQL proxy..."
cloud-sql-proxy --private-ip --port 15432 --auto-iam-authn bh-opie:australia-southeast1:db0 &
PROXY_PID=$!

# Wait for proxy to start
echo "Waiting for Cloud SQL proxy to start..."
for i in {1..30}; do
    if netstat -tlnp 2>/dev/null | grep -q ":15432 "; then
        echo "✅ Cloud SQL proxy started successfully"
        break
    fi
    sleep 2
done

if ! netstat -tlnp 2>/dev/null | grep -q ":15432 "; then
    echo "❌ Cloud SQL proxy failed to start"
    exit 1
fi

# Test connection
echo "Testing database connection..."
if timeout 10 bash -c '</dev/tcp/localhost/15432' 2>/dev/null; then
    echo "✅ Cloud SQL proxy port is accessible"
else
    echo "❌ Cloud SQL proxy port is not accessible"
    exit 1
fi

echo "✅ Cloud SQL proxy test completed successfully"
EOF

chmod +x /tmp/test-cloudsql-proxy.sh

# Check if cloud-sql-proxy binary exists
if command -v cloud-sql-proxy >/dev/null 2>&1; then
    echo "   Cloud SQL proxy binary found, running test..."
    if /tmp/test-cloudsql-proxy.sh; then
        echo "✅ Cloud SQL proxy test passed"
    else
        echo "❌ Cloud SQL proxy test failed"
    fi
else
    echo "⚠️  Cloud SQL proxy binary not found, skipping test"
    echo "   Install with: gcloud components install cloud-sql-proxy"
fi
echo ""

echo "=== Verification Complete ==="
echo ""
echo "Summary:"
echo "- VM Service Account: $VM_SA_EMAIL"
echo "- If any tests failed, check IAM permissions for the VM service account"
echo "- Required roles: cloudsql.client, cloudsql.instanceUser, storage.objectAdmin, artifactregistry.reader, secretmanager.secretAccessor"
echo ""
echo "To fix permission issues, run these commands as a project admin:"
echo "gcloud projects add-iam-policy-binding $PROJECT_ID --member='serviceAccount:$VM_SA_EMAIL' --role='roles/cloudsql.client'"
echo "gcloud projects add-iam-policy-binding $PROJECT_ID --member='serviceAccount:$VM_SA_EMAIL' --role='roles/cloudsql.instanceUser'"
echo "gcloud projects add-iam-policy-binding $PROJECT_ID --member='serviceAccount:$VM_SA_EMAIL' --role='roles/storage.objectAdmin'"
echo "gcloud projects add-iam-policy-binding $PROJECT_ID --member='serviceAccount:$VM_SA_EMAIL' --role='roles/artifactregistry.reader'"
echo "gcloud projects add-iam-policy-binding $PROJECT_ID --member='serviceAccount:$VM_SA_EMAIL' --role='roles/secretmanager.secretAccessor'"
