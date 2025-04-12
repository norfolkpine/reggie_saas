from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from google.cloud import storage


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


def create_gcs_folder(path: str):
    client = storage.Client(credentials=settings.GS_CREDENTIALS)
    bucket = client.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"{path}/.keep")

    if not blob.exists():
        blob.upload_from_string("", content_type="text/plain")
        return True
    return False


def init_user_gcs_structure(user_id: int):
    base = f"reggie-data/users/{user_id}"
    for suffix in ["uploads", "agents", "projects"]:
        create_gcs_folder(f"{base}/{suffix}")


def init_team_gcs_structure(team_id: int):
    base = f"reggie-data/teams/{team_id}"
    for suffix in ["uploads", "projects"]:
        create_gcs_folder(f"{base}/{suffix}")


def init_knowledgebase_gcs_structure(kb_code: str):
    path = f"reggie-data/global/knowledge_base/{kb_code}"
    create_gcs_folder(path)
