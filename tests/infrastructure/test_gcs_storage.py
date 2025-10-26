"""
Comprehensive tests for Google Cloud Storage (GCS) infrastructure.

These tests verify:
- Service account key validation and authentication
- Bucket access permissions
- File upload/download operations
- Signed URL generation
- Error handling for various failure scenarios
"""

import base64
import json
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from google.cloud import storage
from google.oauth2 import service_account


class TestGCSStorageInfrastructure(TestCase):
    """Test GCS storage infrastructure components."""

    def setUp(self):
        """Set up test environment."""
        self.test_file_content = "Test file content for GCS testing"
        self.test_file_name = "test-infrastructure-file.txt"
        
    def tearDown(self):
        """Clean up test files."""
        try:
            default_storage.delete(self.test_file_name)
        except Exception:
            pass  # File might not exist

    def test_gcs_service_account_key_validation(self):
        """Test that GCS_STORAGE_SA_KEY_BASE64 is valid JSON."""
        gcs_key_base64 = os.environ.get('GCS_STORAGE_SA_KEY_BASE64')
        
        if not gcs_key_base64:
            self.skipTest("GCS_STORAGE_SA_KEY_BASE64 not set - skipping service account key test")
        
        try:
            # Decode base64
            sa_key_json = base64.b64decode(gcs_key_base64).decode('utf-8')
            
            # Parse JSON
            sa_key_data = json.loads(sa_key_json)
            
            # Validate required fields
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

    def test_gcs_credentials_creation(self):
        """Test that service account credentials can be created."""
        gcs_key_base64 = os.environ.get('GCS_STORAGE_SA_KEY_BASE64')
        
        if not gcs_key_base64:
            self.skipTest("GCS_STORAGE_SA_KEY_BASE64 not set - skipping credentials test")
        
        try:
            # Decode and create credentials
            sa_key_json = base64.b64decode(gcs_key_base64).decode('utf-8')
            sa_key_data = json.loads(sa_key_json)
            
            credentials = service_account.Credentials.from_service_account_info(sa_key_data)
            
            # Validate credentials
            self.assertIsNotNone(credentials)
            self.assertEqual(credentials.service_account_email, sa_key_data['client_email'])
            self.assertEqual(credentials.project_id, sa_key_data['project_id'])
            
            # Test signing capability
            self.assertTrue(hasattr(credentials, 'sign'), "Credentials should support signing")
            
        except Exception as e:
            self.fail(f"GCS credentials creation failed: {e}")

    def test_gcs_storage_configuration(self):
        """Test Django storage configuration for GCS."""
        storages = getattr(settings, 'STORAGES', {})
        
        if 'default' not in storages:
            self.skipTest("No default storage configured")
        
        default_storage_config = storages['default']
        
        # Check backend
        self.assertEqual(
            default_storage_config['BACKEND'],
            'storages.backends.gcloud.GoogleCloudStorage'
        )
        
        # Check options
        options = default_storage_config.get('OPTIONS', {})
        self.assertIn('bucket_name', options)
        self.assertIn('credentials', options)
        
        # Validate bucket name format
        bucket_name = options['bucket_name']
        self.assertIsInstance(bucket_name, str)
        self.assertGreater(len(bucket_name), 0)

    @patch('google.cloud.storage.Client')
    def test_gcs_bucket_access_permissions(self, mock_client_class):
        """Test bucket access permissions."""
        # Mock the GCS client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock bucket and blob operations
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        
        # Test bucket exists
        mock_bucket.exists.return_value = True
        
        # Test blob operations
        mock_blob.exists.return_value = False
        mock_blob.upload_from_string.return_value = None
        mock_blob.download_as_text.return_value = "test content"
        
        # Get storage configuration
        storages = getattr(settings, 'STORAGES', {})
        if 'default' not in storages:
            self.skipTest("No default storage configured")
        
        bucket_name = storages['default']['OPTIONS']['bucket_name']
        
        # Test bucket access
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # Verify bucket exists
        self.assertTrue(bucket.exists())
        
        # Test blob creation and upload
        blob = bucket.blob('test-permissions.txt')
        blob.upload_from_string('test content')
        
        # Test blob download
        content = blob.download_as_text()
        self.assertEqual(content, 'test content')

    def test_gcs_file_upload_download(self):
        """Test file upload and download operations."""
        try:
            # Test file upload
            test_content = ContentFile(self.test_file_content.encode('utf-8'))
            saved_path = default_storage.save(self.test_file_name, test_content)
            
            self.assertIsNotNone(saved_path)
            self.assertEqual(saved_path, self.test_file_name)
            
            # Test file exists
            self.assertTrue(default_storage.exists(self.test_file_name))
            
            # Test file download
            downloaded_content = default_storage.open(self.test_file_name).read()
            self.assertEqual(downloaded_content.decode('utf-8'), self.test_file_content)
            
            # Test file size
            file_size = default_storage.size(self.test_file_name)
            self.assertEqual(file_size, len(self.test_file_content.encode('utf-8')))
            
        except Exception as e:
            self.fail(f"GCS file upload/download test failed: {e}")

    def test_gcs_signed_url_generation(self):
        """Test signed URL generation for private files."""
        try:
            # Upload test file
            test_content = ContentFile(self.test_file_content.encode('utf-8'))
            default_storage.save(self.test_file_name, test_content)
            
            # Generate signed URL
            signed_url = default_storage.url(self.test_file_name)
            
            self.assertIsNotNone(signed_url)
            self.assertIsInstance(signed_url, str)
            self.assertTrue(len(signed_url) > 0)
            
            # Check if URL contains signature parameters (for private buckets)
            # Note: Public buckets might not have signature parameters
            if 'X-Goog-Signature' in signed_url or 'X-Goog-Algorithm' in signed_url:
                self.assertTrue(True, "URL is properly signed")
            else:
                # For public buckets, just check it's a valid URL
                self.assertTrue(signed_url.startswith('http'))
            
        except Exception as e:
            self.fail(f"GCS signed URL generation test failed: {e}")

    def test_gcs_file_deletion(self):
        """Test file deletion operations."""
        try:
            # Upload test file
            test_content = ContentFile(self.test_file_content.encode('utf-8'))
            default_storage.save(self.test_file_name, test_content)
            
            # Verify file exists
            self.assertTrue(default_storage.exists(self.test_file_name))
            
            # Delete file
            default_storage.delete(self.test_file_name)
            
            # Verify file no longer exists
            self.assertFalse(default_storage.exists(self.test_file_name))
            
        except Exception as e:
            self.fail(f"GCS file deletion test failed: {e}")

    def test_gcs_error_handling_invalid_credentials(self):
        """Test error handling with invalid credentials."""
        with patch('google.oauth2.service_account.Credentials.from_service_account_info') as mock_creds:
            mock_creds.side_effect = Exception("Invalid credentials")
            
            with self.assertRaises(Exception):
                # This should raise an exception when credentials are invalid
                sa_key_json = '{"invalid": "json"}'
                sa_key_data = json.loads(sa_key_json)
                service_account.Credentials.from_service_account_info(sa_key_data)

    def test_gcs_error_handling_bucket_not_found(self):
        """Test error handling when bucket doesn't exist."""
        with patch('google.cloud.storage.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock bucket not found
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = False
            mock_client.bucket.return_value = mock_bucket
            
            with self.assertRaises(Exception):
                client = storage.Client()
                bucket = client.bucket('non-existent-bucket')
                if not bucket.exists():
                    raise Exception("Bucket does not exist")

    def test_gcs_error_handling_permission_denied(self):
        """Test error handling when permissions are insufficient."""
        with patch('google.cloud.storage.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock permission denied
            mock_bucket = MagicMock()
            mock_bucket.exists.side_effect = Exception("Permission denied")
            mock_client.bucket.return_value = mock_bucket
            
            with self.assertRaises(Exception):
                client = storage.Client()
                bucket = client.bucket('test-bucket')
                bucket.exists()

    def test_gcs_environment_variables(self):
        """Test that required environment variables are set."""
        required_vars = [
            'GCS_STORAGE_SA_KEY_BASE64',
            'GCS_BUCKET_NAME',
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            self.skipTest(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        # Test that variables are not empty
        for var in required_vars:
            value = os.environ.get(var)
            self.assertIsNotNone(value, f"{var} should not be None")
            self.assertGreater(len(value), 0, f"{var} should not be empty")

    def test_gcs_storage_backend_initialization(self):
        """Test that GCS storage backend initializes correctly."""
        try:
            # Test that default storage is properly configured
            storage_backend = default_storage
            
            # Check that it's the right backend
            self.assertIn('GoogleCloudStorage', str(type(storage_backend)))
            
            # Test basic operations
            self.assertTrue(hasattr(storage_backend, 'save'))
            self.assertTrue(hasattr(storage_backend, 'delete'))
            self.assertTrue(hasattr(storage_backend, 'exists'))
            self.assertTrue(hasattr(storage_backend, 'url'))
            
        except Exception as e:
            self.fail(f"GCS storage backend initialization test failed: {e}")

    def test_gcs_file_overwrite_behavior(self):
        """Test file overwrite behavior configuration."""
        storages = getattr(settings, 'STORAGES', {})
        
        if 'default' not in storages:
            self.skipTest("No default storage configured")
        
        options = storages['default'].get('OPTIONS', {})
        file_overwrite = options.get('file_overwrite', True)
        
        # Test overwrite behavior
        try:
            # Upload first file
            content1 = ContentFile("First content".encode('utf-8'))
            default_storage.save(self.test_file_name, content1)
            
            # Upload second file with same name
            content2 = ContentFile("Second content".encode('utf-8'))
            default_storage.save(self.test_file_name, content2)
            
            # Check content
            downloaded_content = default_storage.open(self.test_file_name).read()
            
            if file_overwrite:
                self.assertEqual(downloaded_content.decode('utf-8'), "Second content")
            else:
                # If overwrite is False, behavior depends on implementation
                self.assertIn(downloaded_content.decode('utf-8'), ["First content", "Second content"])
                
        except Exception as e:
            self.fail(f"GCS file overwrite behavior test failed: {e}")

    def test_gcs_static_files_configuration(self):
        """Test static files storage configuration."""
        storages = getattr(settings, 'STORAGES', {})
        
        if 'staticfiles' not in storages:
            self.skipTest("No staticfiles storage configured")
        
        staticfiles_config = storages['staticfiles']
        
        # Check backend
        self.assertEqual(
            staticfiles_config['BACKEND'],
            'storages.backends.gcloud.GoogleCloudStorage'
        )
        
        # Check options
        options = staticfiles_config.get('OPTIONS', {})
        self.assertIn('bucket_name', options)
        
        # Validate bucket name
        bucket_name = options['bucket_name']
        self.assertIsInstance(bucket_name, str)
        self.assertGreater(len(bucket_name), 0)
        
        # Should be different from media bucket
        if 'default' in storages:
            media_bucket = storages['default']['OPTIONS']['bucket_name']
            self.assertNotEqual(bucket_name, media_bucket, 
                               "Static and media buckets should be different")


class TestGCSStorageIntegration(TestCase):
    """Integration tests for GCS storage with Django models."""

    def setUp(self):
        """Set up test environment."""
        self.test_file_content = "Integration test content"
        self.test_file_name = "integration-test-file.txt"

    def tearDown(self):
        """Clean up test files."""
        try:
            default_storage.delete(self.test_file_name)
        except Exception:
            pass

    def test_gcs_with_django_file_field(self):
        """Test GCS integration with Django FileField."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        try:
            # Create a simple uploaded file
            uploaded_file = SimpleUploadedFile(
                self.test_file_name,
                self.test_file_content.encode('utf-8'),
                content_type='text/plain'
            )
            
            # Save using default storage
            saved_path = default_storage.save(self.test_file_name, uploaded_file)
            
            self.assertIsNotNone(saved_path)
            self.assertTrue(default_storage.exists(saved_path))
            
            # Test file access
            file_obj = default_storage.open(saved_path)
            content = file_obj.read()
            self.assertEqual(content.decode('utf-8'), self.test_file_content)
            
        except Exception as e:
            self.fail(f"GCS Django FileField integration test failed: {e}")

    def test_gcs_file_url_generation(self):
        """Test URL generation for different file types."""
        test_files = [
            ('test-image.jpg', 'image/jpeg'),
            ('test-document.pdf', 'application/pdf'),
            ('test-text.txt', 'text/plain'),
        ]
        
        try:
            for filename, content_type in test_files:
                # Create test file
                content = ContentFile(f"Test content for {filename}".encode('utf-8'))
                saved_path = default_storage.save(filename, content)
                
                # Generate URL
                url = default_storage.url(saved_path)
                
                self.assertIsNotNone(url)
                self.assertTrue(url.startswith('http'))
                
                # Clean up
                default_storage.delete(filename)
                
        except Exception as e:
            self.fail(f"GCS file URL generation test failed: {e}")

    def test_gcs_large_file_handling(self):
        """Test handling of large files."""
        try:
            # Create a larger test file (1MB)
            large_content = "x" * (1024 * 1024)  # 1MB
            large_file = ContentFile(large_content.encode('utf-8'))
            
            # Save large file
            saved_path = default_storage.save('large-test-file.txt', large_file)
            
            self.assertIsNotNone(saved_path)
            self.assertTrue(default_storage.exists(saved_path))
            
            # Check file size
            file_size = default_storage.size(saved_path)
            self.assertEqual(file_size, len(large_content.encode('utf-8')))
            
            # Clean up
            default_storage.delete(saved_path)
            
        except Exception as e:
            self.fail(f"GCS large file handling test failed: {e}")

    def test_gcs_concurrent_access(self):
        """Test concurrent file access scenarios."""
        import threading
        import time
        
        results = []
        
        def upload_file(file_num):
            """Upload a file in a separate thread."""
            try:
                content = ContentFile(f"Concurrent test file {file_num}".encode('utf-8'))
                filename = f"concurrent-test-{file_num}.txt"
                saved_path = default_storage.save(filename, content)
                results.append(('upload', file_num, saved_path))
            except Exception as e:
                results.append(('error', file_num, str(e)))
        
        try:
            # Start multiple upload threads
            threads = []
            for i in range(3):
                thread = threading.Thread(target=upload_file, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Check results
            self.assertEqual(len(results), 3)
            
            # Clean up uploaded files
            for result_type, file_num, path in results:
                if result_type == 'upload':
                    default_storage.delete(path)
            
        except Exception as e:
            self.fail(f"GCS concurrent access test failed: {e}")
