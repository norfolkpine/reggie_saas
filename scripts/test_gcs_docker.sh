#!/bin/bash
# Test GCS configuration in Docker environment

echo "🧪 Testing GCS Configuration in Docker Environment"
echo "=================================================="

# Test 1: Check environment variables
echo "📋 Environment Variables:"
echo "GCP_SA_KEY_BASE64: ${GCP_SA_KEY_BASE64:-'Not set'}"
echo "GOOGLE_CLOUD_PROJECT: ${GOOGLE_CLOUD_PROJECT:-'Not set'}"

# Test 2: Run Django management command
echo -e "\n🔗 Testing Signed URL Generation:"
docker-compose -f docker-compose.prod.yml exec web python manage.py test_gcs_signed_urls

# Test 3: Check GCS credentials in container
echo -e "\n🔐 Checking GCS Credentials in Container:"
docker-compose -f docker-compose.prod.yml exec web python -c "
import os
import base64
import json
from google.oauth2 import service_account

# Test service account key configuration
gcp_sa_key_base64 = os.environ.get('GCP_SA_KEY_BASE64')
if gcp_sa_key_base64:
    try:
        sa_key_json = base64.b64decode(gcp_sa_key_base64).decode('utf-8')
        sa_key_data = json.loads(sa_key_json)
        credentials = service_account.Credentials.from_service_account_info(sa_key_data)
        print(f'✅ Service account key loaded: {credentials.service_account_email}')
        print(f'✅ Supports signing: {hasattr(credentials, \"sign\")}')
    except Exception as e:
        print(f'❌ Service account key failed: {e}')
else:
    print('⚠️  No GCP_SA_KEY_BASE64 set')
    
    # Fallback to file-based credentials
    if os.path.exists('/tmp/gcp-credentials.json'):
        try:
            credentials = service_account.Credentials.from_service_account_file('/tmp/gcp-credentials.json')
            print(f'✅ Service account file loaded: {credentials.service_account_email}')
            print(f'✅ Supports signing: {hasattr(credentials, \"sign\")}')
        except Exception as e:
            print(f'❌ Service account file failed: {e}')
    else:
        print('⚠️  No service account credentials found')
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
