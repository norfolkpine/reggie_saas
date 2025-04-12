import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from google.cloud import storage


# === Upload via Django's default_storage ===
def upload_to_media_storage(path: str, file) -> str:
    """
    Upload a file to GCS or local media via Django's default_storage.

    Args:
        path (str): e.g., "users/uuid/uploads/file.pdf"
        file: Django UploadedFile or file-like object

    Returns:
        str: Public or signed URL to access the uploaded file
    """
    saved_path = default_storage.save(path, ContentFile(file.read()))
    return default_storage.url(saved_path)


# === Create folder placeholder in GCS ===
def create_gcs_folder(path: str) -> bool:
    client = storage.Client(credentials=settings.GS_CREDENTIALS)
    bucket = client.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(f"{path}/.keep")

    if not blob.exists():
        blob.upload_from_string("", content_type="text/plain")
        return True
    return False


# === Init folders for a user ===
def init_user_gcs_structure(user_id: int, user_uuid: uuid.UUID):
    folder = f"{user_id}-{user_uuid.hex}"
    base = f"reggie-data/users/{folder}"
    for suffix in ["uploads", "agents", "projects"]:
        create_gcs_folder(f"{base}/{suffix}")


# === Init folders for a team ===
def init_team_gcs_structure(team_id: int, team_uuid: uuid.UUID):
    folder = f"{team_id}-{team_uuid.hex}"
    base = f"reggie-data/teams/{folder}"
    for suffix in ["uploads", "projects"]:
        create_gcs_folder(f"{base}/{suffix}")


# === Init folder for a knowledge base ===
def init_knowledgebase_gcs_structure(kb_code: str):
    create_gcs_folder(f"reggie-data/global/knowledge_base/{kb_code}")


# === Determine file path for uploaded document ===
def user_document_path(instance, filename: str) -> str:
    user = instance.uploaded_by
    user_folder = f"{user.id}-{user.uuid.hex}" if user else "anonymous"
    return f"reggie-data/users/{user_folder}/uploads/{filename}"
