# app_integrations/urls.py
from django.urls import path
from .views.google_drive import google_oauth_start, google_oauth_callback, list_google_drive_files, upload_file_to_google_drive, download_file_from_google_drive, create_google_doc_from_markdown, revoke_google_drive_access

urlpatterns = [
    path("gdrive/oauth/start/", google_oauth_start, name="google_oauth_start"),
    path("gdrive/oauth/callback/", google_oauth_callback, name="google_oauth_callback"),
    path("gdrive/revoke/", revoke_google_drive_access, name="gdrive_revoke"),
    path("gdrive/files/", list_google_drive_files, name="google_drive_files"),
    path("gdrive/upload/", upload_file_to_google_drive, name="gdrive_upload"),
    path("gdrive/download/<str:file_id>/", download_file_from_google_drive, name="gdrive_download"),
    path("gdrive/docs/markdown/", create_google_doc_from_markdown, name="gdrive_docs_from_markdown"),
]
