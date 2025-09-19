"""
Utility functions for generating signed URLs for file access.
Works with Django's storage backends (GCS, S3, local filesystem).
Designed for use by AI agents to generate proper file access URLs.
"""

import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_signed_url(
    file_path: str, 
    expiration_hours: int = 1, 
    method: str = "GET",
    content_type: Optional[str] = None
) -> Optional[str]:
    """
    Generate a signed URL for accessing a file stored in cloud storage.
    Uses Django's storage backend to handle different storage providers.
    
    Args:
        file_path: Path to the file in storage (e.g., 'media/user_files/123/file.pdf')
        expiration_hours: Number of hours until the URL expires (default: 1)
        method: HTTP method allowed (default: 'GET')
        content_type: Optional content type for the file
        
    Returns:
        Signed URL string or None if generation fails
    """
    try:
        # Get the storage backend
        storage = default_storage
        
        # Calculate expiration time
        expiration_time = timezone.now() + timedelta(hours=expiration_hours)
        
        # Check if storage backend supports signed URLs
        if hasattr(storage, 'url') and callable(getattr(storage, 'url', None)):
            # For local storage or simple backends, return direct URL
            if not _is_cloud_storage(storage):
                logger.info(f"Local storage detected, returning direct URL for {file_path}")
                return storage.url(file_path)
        
        # Generate signed URL based on storage backend
        if _is_gcs_storage(storage):
            return _generate_gcs_signed_url(
                storage, file_path, expiration_time, method, content_type
            )
        elif _is_s3_storage(storage):
            return _generate_s3_signed_url(
                storage, file_path, expiration_time, method, content_type
            )
        else:
            # Fallback to direct URL
            logger.warning(f"Unknown storage backend, returning direct URL for {file_path}")
            return storage.url(file_path)
            
    except Exception as e:
        logger.error(f"Failed to generate signed URL for {file_path}: {str(e)}")
        return None


def _is_cloud_storage(storage) -> bool:
    """Check if storage backend is a cloud storage provider."""
    return _is_gcs_storage(storage) or _is_s3_storage(storage)


def _is_gcs_storage(storage) -> bool:
    """Check if storage backend is Google Cloud Storage."""
    return (
        hasattr(storage, 'bucket_name') and 
        hasattr(storage, 'client') and
        ('gcloud' in str(type(storage).__module__) or 'gcloud' in str(storage.__class__))
    )


def _is_s3_storage(storage) -> bool:
    """Check if storage backend is Amazon S3."""
    return (
        hasattr(storage, 'bucket_name') and 
        hasattr(storage, 'connection') and
        's3' in str(type(storage).__module__).lower()
    )


def _generate_gcs_signed_url(
    storage, 
    file_path: str, 
    expiration_time, 
    method: str, 
    content_type: Optional[str]
) -> Optional[str]:
    """Generate signed URL for Google Cloud Storage using django-storages."""
    try:
        # Use django-storages GCS backend's built-in signed URL generation
        if hasattr(storage, 'url') and callable(getattr(storage, 'url', None)):
            # Try to use the storage backend's built-in method
            try:
                # For django-storages GCS, we can use the url method with signed=True
                if hasattr(storage, 'url') and 'signed' in storage.url.__code__.co_varnames:
                    return storage.url(file_path, signed=True, expiration=expiration_time)
            except (TypeError, AttributeError):
                pass
        
        # Fallback to manual GCS client approach
        from google.cloud import storage as gcs_client
        from google.auth import default
        
        # Get GCS client
        if hasattr(storage, 'client'):
            client = storage.client
        else:
            # Create client using credentials from storage or default credentials
            credentials = getattr(storage, 'credentials', None)
            if credentials:
                client = gcs_client.Client(credentials=credentials)
            else:
                # Use default credentials (works in GCP environments)
                try:
                    credentials, project = default()
                    client = gcs_client.Client(credentials=credentials, project=project)
                except Exception as e:
                    logger.error(f"Failed to get default GCS credentials: {str(e)}")
                    return None
        
        # Get bucket
        bucket_name = storage.bucket_name
        bucket = client.bucket(bucket_name)
        
        # Clean up file path - remove bucket name if it's included
        clean_file_path = file_path
        if file_path.startswith(f"{bucket_name}/"):
            clean_file_path = file_path[len(f"{bucket_name}/"):]
        
        # Get blob
        blob = bucket.blob(clean_file_path)
        
        # Check if blob exists
        if not blob.exists():
            logger.error(f"File {clean_file_path} does not exist in bucket {bucket_name}")
            return None
        
        # Generate signed URL
        url = blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method=method,
            content_type=content_type
        )
        
        logger.info(f"Generated GCS signed URL for {file_path}")
        return url
        
    except Exception as e:
        logger.error(f"Failed to generate GCS signed URL: {str(e)}")
        return None


def _generate_s3_signed_url(
    storage, 
    file_path: str, 
    expiration_time, 
    method: str, 
    content_type: Optional[str]
) -> Optional[str]:
    """Generate signed URL for Amazon S3 using django-storages."""
    try:
        # Use django-storages S3 backend's built-in signed URL generation
        if hasattr(storage, 'url') and callable(getattr(storage, 'url', None)):
            try:
                # For django-storages S3, we can use the url method with signed=True
                if hasattr(storage, 'url') and 'signed' in storage.url.__code__.co_varnames:
                    return storage.url(file_path, signed=True, expiration=expiration_time)
            except (TypeError, AttributeError):
                pass
        
        # Fallback to manual S3 client approach
        import boto3
        from botocore.exceptions import ClientError
        
        # Get S3 client
        s3_client = storage.connection.meta.client
        
        # Generate signed URL
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': storage.bucket_name,
                'Key': file_path,
                'ResponseContentType': content_type
            },
            ExpiresIn=int((expiration_time - timezone.now()).total_seconds())
        )
        
        logger.info(f"Generated S3 signed URL for {file_path}")
        return url
        
    except Exception as e:
        logger.error(f"Failed to generate S3 signed URL: {str(e)}")
        return None


def get_file_content_type(file_path: str) -> str:
    """
    Get content type for a file based on its extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        MIME type string
    """
    import mimetypes
    
    content_type, _ = mimetypes.guess_type(file_path)
    return content_type or 'application/octet-stream'


def get_file_url(file_path: str, signed: bool = False, expiration_hours: int = 1) -> str:
    """
    Get a file URL, optionally signed for cloud storage.
    This is the main function for AI agents to use.
    
    Args:
        file_path: Path to the file in storage
        signed: Whether to generate a signed URL (for cloud storage)
        expiration_hours: Hours until signed URL expires (if signed=True)
        
    Returns:
        File URL (signed or direct)
    """
    if signed:
        signed_url = generate_signed_url(file_path, expiration_hours)
        if signed_url:
            return signed_url
    
    # For direct URLs, clean the path if it includes bucket name
    clean_file_path = file_path
    if hasattr(default_storage, 'bucket_name') and file_path.startswith(f"{default_storage.bucket_name}/"):
        clean_file_path = file_path[len(f"{default_storage.bucket_name}/"):]
    
    # Fallback to direct URL
    return default_storage.url(clean_file_path)


def validate_file_access(file_path: str, user) -> bool:
    """
    Validate that a user has access to a file.
    This is a basic implementation - should be enhanced based on your access control needs.
    
    Args:
        file_path: Path to the file
        user: User requesting access
        
    Returns:
        True if user has access, False otherwise
    """
    # Basic validation - check if file path is in allowed directories
    allowed_prefixes = [
        'media/user_files/',
        'media/vault/',
        'media/global/',
    ]
    
    # Check if file path starts with any allowed prefix
    for prefix in allowed_prefixes:
        if file_path.startswith(prefix):
            return True
    
    logger.warning(f"File access denied for {file_path} - not in allowed directories")
    return False
