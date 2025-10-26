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
project_root = Path(__file__).parent
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
    
    # Test 1: Check if GCS credentials are loaded
    try:
        from google.auth import default
        credentials, project = default()
        print(f"✅ Default credentials loaded: {type(credentials).__name__}")
        print(f"✅ Project: {project}")
        
        # Check if credentials have signing capability
        if hasattr(credentials, 'sign'):
            print("✅ Credentials support signing")
        else:
            print("❌ Credentials do NOT support signing")
            
    except Exception as e:
        print(f"❌ Failed to load default credentials: {e}")
        return False
    
    # Test 2: Check service account impersonation
    impersonation_target = os.environ.get('GCS_IMPERSONATION_TARGET')
    if impersonation_target:
        print(f"\n🔐 Testing Service Account Impersonation...")
        print(f"Target: {impersonation_target}")
        
        try:
            from google.auth import impersonated_credentials
            impersonated_creds = impersonated_credentials.Credentials(
                source_credentials=credentials,
                target_principal=impersonation_target,
                target_scopes=['https://www.googleapis.com/auth/devstorage.read_write'],
                lifetime=3600
            )
            print("✅ Service account impersonation configured successfully")
            
            # Test signing with impersonated credentials
            if hasattr(impersonated_creds, 'sign'):
                print("✅ Impersonated credentials support signing")
            else:
                print("❌ Impersonated credentials do NOT support signing")
                
        except Exception as e:
            print(f"❌ Service account impersonation failed: {e}")
    else:
        print("\n⚠️  No GCS_IMPERSONATION_TARGET set")
    
    # Test 3: Check base64 service account key fallback
    gcp_sa_key_base64 = os.environ.get('GCP_SA_KEY_BASE64')
    if gcp_sa_key_base64:
        print(f"\n🔑 Testing Base64 Service Account Key...")
        try:
            import base64
            import json
            from google.oauth2 import service_account
            
            sa_key_json = base64.b64decode(gcp_sa_key_base64).decode('utf-8')
            sa_key_data = json.loads(sa_key_json)
            
            sa_credentials = service_account.Credentials.from_service_account_info(sa_key_data)
            print("✅ Base64 service account key loaded successfully")
            
            if hasattr(sa_credentials, 'sign'):
                print("✅ Service account key credentials support signing")
            else:
                print("❌ Service account key credentials do NOT support signing")
                
        except Exception as e:
            print(f"❌ Base64 service account key failed: {e}")
    else:
        print("\n⚠️  No GCP_SA_KEY_BASE64 set")
    
    # Test 4: Check file-based service account key
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
    
    # Test 5: Test Django storage configuration
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
                else:
                    print("❌ No credentials in storage options")
        else:
            print("❌ No default storage configured")
            
    except Exception as e:
        print(f"❌ Django storage configuration test failed: {e}")
    
    # Test 6: Test signed URL generation (if possible)
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
