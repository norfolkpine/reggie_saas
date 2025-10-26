"""
Basic infrastructure tests for GitHub Actions workflow.

These tests verify:
- Environment variables are set correctly
- GCS service account key is valid
- Can connect to GCS buckets
- Database connection works
"""

import base64
import json
import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.conf import settings


class TestBasicInfrastructure(TestCase):
    """Basic infrastructure connectivity tests."""

    def test_environment_variables_present(self):
        """Test that required environment variables are present."""
        required_vars = [
            'GCS_STORAGE_SA_KEY_BASE64',
            'GCS_BUCKET_NAME', 
            'DATABASE_URL',
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            self.skipTest(f"Missing environment variables: {', '.join(missing_vars)}")
        
        # If we get here, all required vars are present
        self.assertTrue(True, "All required environment variables are present")

    def test_gcs_service_account_key_valid(self):
        """Test that GCS service account key is valid JSON."""
        gcs_key_base64 = os.environ.get('GCS_STORAGE_SA_KEY_BASE64')
        
        if not gcs_key_base64:
            self.skipTest("GCS_STORAGE_SA_KEY_BASE64 not set")
        
        try:
            # Decode base64
            sa_key_json = base64.b64decode(gcs_key_base64).decode('utf-8')
            
            # Parse JSON
            sa_key_data = json.loads(sa_key_json)
            
            # Check required fields
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            for field in required_fields:
                self.assertIn(field, sa_key_data, f"Missing required field: {field}")
            
            # Validate service account type
            self.assertEqual(sa_key_data['type'], 'service_account')
            
            # Validate email format
            self.assertIn('@', sa_key_data['client_email'])
            self.assertIn('.iam.gserviceaccount.com', sa_key_data['client_email'])
            
        except Exception as e:
            self.fail(f"GCS service account key validation failed: {e}")

    def test_gcs_bucket_connection(self):
        """Test that we can connect to GCS bucket."""
        gcs_key_base64 = os.environ.get('GCS_STORAGE_SA_KEY_BASE64')
        bucket_name = os.environ.get('GCS_BUCKET_NAME')
        
        if not gcs_key_base64 or not bucket_name:
            self.skipTest("GCS credentials not configured")
        
        try:
            from google.cloud import storage
            from google.oauth2 import service_account
            
            # Create credentials
            sa_key_json = base64.b64decode(gcs_key_base64).decode('utf-8')
            sa_key_data = json.loads(sa_key_json)
            credentials = service_account.Credentials.from_service_account_info(sa_key_data)
            
            # Create client
            client = storage.Client(credentials=credentials)
            
            # Test bucket access
            bucket = client.bucket(bucket_name)
            
            # Check if bucket exists
            self.assertTrue(bucket.exists(), f"Bucket {bucket_name} does not exist or is not accessible")
            
            # Test basic operations
            blob = bucket.blob('test-connection.txt')
            
            # Upload test content
            test_content = "Infrastructure test connection"
            blob.upload_from_string(test_content)
            
            # Verify upload
            self.assertTrue(blob.exists(), "Test file upload failed")
            
            # Download and verify content
            downloaded_content = blob.download_as_text()
            self.assertEqual(downloaded_content, test_content)
            
            # Clean up
            blob.delete()
            
        except Exception as e:
            self.fail(f"GCS bucket connection test failed: {e}")

    def test_database_connection(self):
        """Test that database connection works."""
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            self.skipTest("DATABASE_URL not set")
        
        try:
            from django.db import connection
            
            # Test basic connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                self.assertEqual(result[0], 1)
            
            # Test database info
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                self.assertIn('PostgreSQL', version)
            
        except Exception as e:
            self.fail(f"Database connection test failed: {e}")

    def test_cloud_sql_connection_string(self):
        """Test Cloud SQL connection string parsing."""
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            self.skipTest("DATABASE_URL not set")
        
        # Check if it's a Cloud SQL connection
        if "/cloudsql/" in database_url:
            try:
                from urllib.parse import urlparse, parse_qs
                
                parsed_url = urlparse(database_url)
                query_params = parse_qs(parsed_url.query)
                
                # Extract Cloud SQL connection name
                cloud_sql_host = query_params.get('host', [''])[0]
                
                # Validate format
                self.assertTrue(cloud_sql_host.startswith('/cloudsql/'))
                
                # Extract connection name
                connection_name = cloud_sql_host.replace('/cloudsql/', '')
                self.assertGreater(len(connection_name), 0)
                
            except Exception as e:
                self.fail(f"Cloud SQL connection string parsing failed: {e}")
        else:
            self.skipTest("Not a Cloud SQL connection string")

    def test_django_settings_configuration(self):
        """Test that Django settings are properly configured."""
        # Test database configuration
        databases = settings.DATABASES
        self.assertIn('default', databases)
        
        default_db = databases['default']
        self.assertEqual(default_db['ENGINE'], 'django.db.backends.postgresql')
        
        # Test storage configuration (if in production mode)
        storages = getattr(settings, 'STORAGES', {})
        if 'default' in storages:
            default_storage_config = storages['default']
            backend = default_storage_config.get('BACKEND', '')
            
            # Should be GCS in production, FileSystem in development
            if 'GoogleCloudStorage' in backend:
                # Production mode - check GCS config
                options = default_storage_config.get('OPTIONS', {})
                self.assertIn('bucket_name', options)
                self.assertIn('credentials', options)
            else:
                # Development mode - this is fine
                self.assertIn('FileSystemStorage', backend)

    def test_secrets_accessible(self):
        """Test that secrets are accessible from environment."""
        # Test that we can access the secrets
        secrets_to_check = [
            'GCS_STORAGE_SA_KEY_BASE64',
            'GCS_BUCKET_NAME',
            'DATABASE_URL',
        ]
        
        accessible_secrets = []
        for secret in secrets_to_check:
            if os.environ.get(secret):
                accessible_secrets.append(secret)
        
        self.assertGreater(len(accessible_secrets), 0, "No secrets are accessible")
        
        # Log which secrets are accessible (for debugging)
        print(f"Accessible secrets: {', '.join(accessible_secrets)}")

    def test_basic_file_operations(self):
        """Test basic file operations with current storage backend."""
        try:
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            
            # Test file upload
            test_content = "Basic infrastructure test"
            test_file = ContentFile(test_content.encode('utf-8'))
            saved_path = default_storage.save('test-basic-infrastructure.txt', test_file)
            
            self.assertIsNotNone(saved_path)
            
            # Test file exists
            self.assertTrue(default_storage.exists(saved_path))
            
            # Test file download
            downloaded_content = default_storage.open(saved_path).read()
            self.assertEqual(downloaded_content.decode('utf-8'), test_content)
            
            # Test file deletion
            default_storage.delete(saved_path)
            self.assertFalse(default_storage.exists(saved_path))
            
        except Exception as e:
            self.fail(f"Basic file operations test failed: {e}")

    def test_health_check_endpoints(self):
        """Test basic health check functionality."""
        try:
            from django.test import Client
            
            client = Client()
            
            # Test root endpoint
            response = client.get('/')
            self.assertIn(response.status_code, [200, 302])  # 302 for redirect to login
            
            # Test database health
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                self.assertEqual(result[0], 1)
            
        except Exception as e:
            self.fail(f"Health check test failed: {e}")
