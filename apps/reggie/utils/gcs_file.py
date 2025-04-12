from datetime import timedelta

from django.conf import settings
from google.cloud import storage


def get_gcs_client():
    return storage.Client()


def upload_file_to_gcs(bucket_name, file_obj, destination_blob_path, content_type=None):
    """
    Uploads a file-like object to GCS.

    Args:
        bucket_name (str): GCS bucket name.
        file_obj (file): Django InMemoryUploadedFile or similar.
        destination_blob_path (str): Path in the bucket, e.g., 'users/123/uploads/file.pdf'
        content_type (str): Optional content type for metadata.

    Returns:
        str: Public or signed URL to the file.
    """
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_path)
    blob.upload_from_file(file_obj, content_type=content_type or file_obj.content_type)

    # Optional: Make public or generate signed URL
    if getattr(settings, "GCS_SIGNED_URLS", False):
        return blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")
    elif getattr(settings, "GCS_PUBLIC_READ", False):
        blob.make_public()
        return blob.public_url

    return f"gs://{bucket_name}/{destination_blob_path}"
