#!/bin/bash
# Test GCS configuration in Docker environment

echo "🧪 Testing GCS Configuration in Docker Environment"
echo "=================================================="

# Test 1: Check environment variables
echo "📋 Environment Variables:"
echo "GCS_IMPERSONATION_TARGET: ${GCS_IMPERSONATION_TARGET:-'Not set'}"
echo "GCP_SA_KEY_BASE64: ${GCP_SA_KEY_BASE64:+Set (${#GCP_SA_KEY_BASE64} chars)}"
echo "GOOGLE_CLOUD_PROJECT: ${GOOGLE_CLOUD_PROJECT:-'Not set'}"

# Test 2: Run Django management command
echo -e "\n🔗 Testing Signed URL Generation:"
docker-compose -f docker-compose.prod.yml exec web python manage.py test_gcs_signed_urls

# Test 3: Check GCS credentials in container
echo -e "\n🔐 Checking GCS Credentials in Container:"
docker-compose -f docker-compose.prod.yml exec web python -c "
import os
from google.auth import default
try:
    credentials, project = default()
    print(f'✅ Credentials loaded: {type(credentials).__name__}')
    print(f'✅ Project: {project}')
    print(f'✅ Supports signing: {hasattr(credentials, \"sign\")}')
except Exception as e:
    print(f'❌ Failed to load credentials: {e}')
"

# Test 4: Test file upload/download
echo -e "\n📁 Testing File Upload/Download:"
docker-compose -f docker-compose.prod.yml exec web python -c "
from django.core.files.storage import default_storage
import tempfile

# Create a test file
from django.core.files.base import ContentFile
test_content = 'Test content for GCS integration test'
test_file = 'integration-test.txt'

try:
    # Upload file
    default_storage.save(test_file, ContentFile(test_content.encode('utf-8')))
    print('✅ File uploaded successfully')
    
    # Generate URL
    url = default_storage.url(test_file)
    print(f'✅ URL generated: {url[:100]}...')
    
    # Download file
    downloaded_content = default_storage.open(test_file).read()
    if downloaded_content == test_content:
        print('✅ File download successful')
    else:
        print('❌ File content mismatch')
    
    # Clean up
    default_storage.delete(test_file)
    print('✅ Test file cleaned up')
    
except Exception as e:
    print(f'❌ File test failed: {e}')
"

echo -e "\n🏁 Docker GCS Test Complete!"
