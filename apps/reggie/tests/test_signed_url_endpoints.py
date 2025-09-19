"""
Tests for signed URL utility functions.
"""

from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.files.storage import default_storage

User = get_user_model()


class SignedURLUtilsTestCase(TestCase):
    """Test the signed URL utility functions."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )

    def test_get_file_content_type(self):
        """Test content type detection."""
        from apps.reggie.utils.signed_url_utils import get_file_content_type
        
        # Test PDF file
        content_type = get_file_content_type("test.pdf")
        self.assertEqual(content_type, "application/pdf")
        
        # Test text file
        content_type = get_file_content_type("test.txt")
        self.assertEqual(content_type, "text/plain")
        
        # Test unknown file
        content_type = get_file_content_type("test.unknown")
        self.assertEqual(content_type, "application/octet-stream")

    def test_validate_file_access(self):
        """Test file access validation."""
        from apps.reggie.utils.signed_url_utils import validate_file_access
        
        # Test allowed paths
        self.assertTrue(validate_file_access("media/user_files/test.pdf", self.user))
        self.assertTrue(validate_file_access("media/vault/test.pdf", self.user))
        self.assertTrue(validate_file_access("media/global/test.pdf", self.user))
        
        # Test disallowed paths
        self.assertFalse(validate_file_access("etc/passwd", self.user))
        self.assertFalse(validate_file_access("../secret.txt", self.user))
        self.assertFalse(validate_file_access("", self.user))

    def test_get_file_url_direct(self):
        """Test getting direct file URL."""
        from apps.reggie.utils.signed_url_utils import get_file_url
        
        file_path = "media/user_files/test.pdf"
        
        with patch.object(default_storage, 'url') as mock_url:
            mock_url.return_value = "https://example.com/media/user_files/test.pdf"
            
            url = get_file_url(file_path, signed=False)
            
            self.assertEqual(url, "https://example.com/media/user_files/test.pdf")
            mock_url.assert_called_once_with(file_path)

    def test_get_file_url_signed_success(self):
        """Test getting signed file URL when generation succeeds."""
        from apps.reggie.utils.signed_url_utils import get_file_url, generate_signed_url
        
        file_path = "media/user_files/test.pdf"
        expected_signed_url = "https://storage.example.com/signed-url"
        
        with patch('apps.reggie.utils.signed_url_utils.generate_signed_url') as mock_generate:
            mock_generate.return_value = expected_signed_url
            
            url = get_file_url(file_path, signed=True, expiration_hours=2)
            
            self.assertEqual(url, expected_signed_url)
            mock_generate.assert_called_once_with(file_path, 2)

    def test_get_file_url_signed_fallback(self):
        """Test getting direct URL when signed URL generation fails."""
        from apps.reggie.utils.signed_url_utils import get_file_url
        
        file_path = "media/user_files/test.pdf"
        expected_direct_url = "https://example.com/media/user_files/test.pdf"
        
        with patch('apps.reggie.utils.signed_url_utils.generate_signed_url') as mock_generate:
            mock_generate.return_value = None  # Simulate failure
            
            with patch.object(default_storage, 'url') as mock_url:
                mock_url.return_value = expected_direct_url
                
                url = get_file_url(file_path, signed=True)
                
                self.assertEqual(url, expected_direct_url)
                mock_generate.assert_called_once()
                mock_url.assert_called_once_with(file_path)

    @patch('apps.reggie.utils.signed_url_utils.default_storage')
    def test_generate_signed_url_local_storage(self, mock_storage):
        """Test signed URL generation with local storage."""
        from apps.reggie.utils.signed_url_utils import generate_signed_url, _is_cloud_storage
        
        # Mock local storage
        mock_storage.url.return_value = "https://example.com/media/test.pdf"
        
        # Mock the storage detection
        with patch('apps.reggie.utils.signed_url_utils._is_cloud_storage', return_value=False):
            url = generate_signed_url("media/test.pdf")
            
            self.assertEqual(url, "https://example.com/media/test.pdf")
            mock_storage.url.assert_called_once_with("media/test.pdf")

    @patch('apps.reggie.utils.signed_url_utils.default_storage')
    def test_generate_signed_url_gcs_storage(self, mock_storage):
        """Test signed URL generation with GCS storage."""
        from apps.reggie.utils.signed_url_utils import generate_signed_url, _is_gcs_storage
        
        # Mock GCS storage
        mock_storage.bucket_name = "test-bucket"
        mock_storage.client = MagicMock()
        
        # Mock blob and signed URL generation
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"
        
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage.client.bucket.return_value = mock_bucket
        
        with patch('apps.reggie.utils.signed_url_utils._is_gcs_storage', return_value=True):
            url = generate_signed_url("media/test.pdf")
            
            self.assertEqual(url, "https://storage.googleapis.com/signed-url")
            mock_blob.generate_signed_url.assert_called_once()

    def test_storage_detection(self):
        """Test storage backend detection."""
        from apps.reggie.utils.signed_url_utils import _is_gcs_storage, _is_s3_storage, _is_cloud_storage
        
        # Test GCS storage detection
        gcs_storage = MagicMock()
        gcs_storage.bucket_name = "test-bucket"
        gcs_storage.client = MagicMock()
        gcs_storage.__class__.__module__ = "storages.backends.gcloud"
        
        self.assertTrue(_is_gcs_storage(gcs_storage))
        self.assertFalse(_is_s3_storage(gcs_storage))
        self.assertTrue(_is_cloud_storage(gcs_storage))
        
        # Test S3 storage detection
        s3_storage = MagicMock()
        s3_storage.bucket_name = "test-bucket"
        s3_storage.connection = MagicMock()
        s3_storage.__class__.__module__ = "storages.backends.s3boto3"
        
        self.assertFalse(_is_gcs_storage(s3_storage))
        self.assertTrue(_is_s3_storage(s3_storage))
        self.assertTrue(_is_cloud_storage(s3_storage))
        
        # Test local storage detection
        local_storage = MagicMock()
        local_storage.__class__.__module__ = "django.core.files.storage"
        
        self.assertFalse(_is_gcs_storage(local_storage))
        self.assertFalse(_is_s3_storage(local_storage))
        self.assertFalse(_is_cloud_storage(local_storage))
