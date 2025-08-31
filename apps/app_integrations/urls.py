# app_integrations/urls.py
from django.urls import path

from .views.google_drive import (
    create_google_doc_from_markdown,
    download_file_from_google_drive,
    google_oauth_callback,
    google_oauth_start,
    list_google_drive_files,
    revoke_google_drive_access,
    upload_file_to_google_drive,
)
from .views.views import list_supported_apps
from .views.nango_views import (
    initiate_nango_auth,
    nango_callback,
    list_connections,
    disconnect_integration,
    sync_connection,
    proxy_api_request,
)

app_name = 'app_integrations'

urlpatterns = [
    # Nango integration endpoints
    path("nango/auth/", initiate_nango_auth, name="nango_auth"),
    path("nango/callback/", nango_callback, name="nango_callback"),
    path("nango/connections/", list_connections, name="nango_connections"),
    path("nango/connections/<int:connection_id>/disconnect/", disconnect_integration, name="nango_disconnect"),
    path("nango/connections/<int:connection_id>/sync/", sync_connection, name="nango_sync"),
    path("nango/proxy/", proxy_api_request, name="nango_proxy"),
    
    # Legacy Google Drive endpoints (kept for backward compatibility)
    path("gdrive/oauth/start/", google_oauth_start, name="google_oauth_start"),
    path("gdrive/oauth/callback/", google_oauth_callback, name="google_oauth_callback"),
    path("gdrive/revoke/", revoke_google_drive_access, name="gdrive_revoke"),
    path("gdrive/files/", list_google_drive_files, name="google_drive_files"),
    path("gdrive/upload/", upload_file_to_google_drive, name="gdrive_upload"),
    path("gdrive/download/<str:file_id>/", download_file_from_google_drive, name="gdrive_download"),
    path("gdrive/docs/markdown/", create_google_doc_from_markdown, name="gdrive_docs_from_markdown"),
    path("apps/", list_supported_apps, name="list-supported-apps"),
]
