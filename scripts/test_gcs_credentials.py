#!/usr/bin/env python3
"""
Test script for GCS credential loading and signing functionality.
Run this to verify the GCS configuration works correctly.
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bh_opie.settings')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Production')

# Configure Django
from configurations import importer
importer.install()

# Now import Django settings
from django.conf import settings

def test_gcs_credentials():
    """Test GCS credential loading and signing capabilities."""
    print("🧪 Testing GCS Credential Loading...")
    print("=" * 50)
    
    # Test 1: Check service account key configuration (primary method)
    gcp_sa_key_base64 = os.environ.get('GCP_SA_KEY_BASE64')
    if gcp_sa_key_base64:
        print(f"\n🔐 Testing Service Account Key Configuration...")
        try:
            import base64
            import json
            from google.oauth2 import service_account
            
            # Decode the base64 service account key
            sa_key_json = base64.b64decode(gcp_sa_key_base64).decode('utf-8')
            sa_key_data = json.loads(sa_key_json)
            
            # Create credentials from service account info
            credentials = service_account.Credentials.from_service_account_info(sa_key_data)
            print(f"✅ Service account key configured successfully")
            print(f"Service account email: {credentials.service_account_email}")
            
            # Test signing capabilities
            if hasattr(credentials, 'sign'):
                print("✅ Service account credentials support signing")
            else:
                print("❌ Service account credentials do NOT support signing")
                
        except Exception as e:
            print(f"❌ Service account key configuration failed: {e}")
            return False
    else:
        print("\n⚠️  No GCP_SA_KEY_BASE64 set")
    
    # Test 2: Check file-based service account key (fallback)
    sa_key_file = '/tmp/gcp-credentials.json'
    if os.path.exists(sa_key_file):
        print(f"\n📁 Testing Service Account Key File...")
        try:
            from google.oauth2 import service_account
            
            sa_credentials = service_account.Credentials.from_service_account_file(sa_key_file)
            print("✅ Service account key file loaded successfully")
            
            if hasattr(sa_credentials, 'sign'):
                print("✅ Service account key file credentials support signing")
            else:
                print("❌ Service account key file credentials do NOT support signing")
                
        except Exception as e:
            print(f"❌ Service account key file failed: {e}")
    else:
        print(f"\n⚠️  No service account key file found at {sa_key_file}")
    
    # Test 3: Test Django storage configuration
    print(f"\n🗄️  Testing Django Storage Configuration...")
    try:
        storages = getattr(settings, 'STORAGES', {})
        if 'default' in storages:
            default_storage = storages['default']
            print(f"✅ Default storage backend: {default_storage.get('BACKEND', 'Not set')}")
            
            if 'OPTIONS' in default_storage:
                options = default_storage['OPTIONS']
                print(f"✅ Bucket name: {options.get('bucket_name', 'Not set')}")
                print(f"✅ File overwrite: {options.get('file_overwrite', 'Not set')}")
                print(f"✅ Default ACL: {options.get('default_acl', 'Not set')}")
                
                if 'credentials' in options:
                    creds = options['credentials']
                    print(f"✅ Credentials type: {type(creds).__name__}")
                    if hasattr(creds, 'service_account_email'):
                        print(f"✅ Service account email: {creds.service_account_email}")
                else:
                    print("❌ No credentials in storage options")
        else:
            print("❌ No default storage configured")
            
    except Exception as e:
        print(f"❌ Django storage configuration test failed: {e}")
    
    # Test 4: Test signed URL generation (if possible)
    print(f"\n🔗 Testing Signed URL Generation...")
    try:
        from django.core.files.storage import default_storage
        
        # Try to generate a signed URL for a test file
        test_file_path = 'test-signed-url.txt'
        
        # Create a test file
        from django.core.files.base import ContentFile
        test_content = "Test content for signed URL"
        default_storage.save(test_file_path, ContentFile(test_content.encode('utf-8')))
        print(f"✅ Test file created: {test_file_path}")
        
        # Try to generate signed URL
        try:
            signed_url = default_storage.url(test_file_path)
            print(f"✅ Signed URL generated: {signed_url[:100]}...")
            
            # Clean up test file
            default_storage.delete(test_file_path)
            print("✅ Test file cleaned up")
            
        except Exception as e:
            print(f"❌ Signed URL generation failed: {e}")
            # Clean up test file even if URL generation failed
            try:
                default_storage.delete(test_file_path)
            except:
                pass
                
    except Exception as e:
        print(f"❌ Signed URL test failed: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 GCS Credential Testing Complete!")
    return True

if __name__ == "__main__":
    test_gcs_credentials()
