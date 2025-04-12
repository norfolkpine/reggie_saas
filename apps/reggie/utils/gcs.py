from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

def upload_to_media_storage(path: str, file) -> str:
    """
    Uploads a file to GCS or local media storage via Django's default_storage.

    Args:
        path (str): Relative path like "users/123/uploads/myfile.pdf"
        file: Django UploadedFile or file-like object

    Returns:
        str: Full URL to access the uploaded file
    """
    # Save file to constructed path
    saved_path = default_storage.save(path, ContentFile(file.read()))

    # Return full URL
    return default_storage.url(saved_path)
