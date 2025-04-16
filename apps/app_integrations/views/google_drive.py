import json
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect
from django.utils.timezone import now, timedelta
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.template.loader import render_to_string

from apps.app_integrations.models import ConnectedApp, SupportedApp
from apps.app_integrations.utils.markdown_to_google_docs import markdown_to_google_docs_requests

# ================================
# GOOGLE OAUTH FLOW
# ================================


@extend_schema(tags=["Google Drive"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_oauth_start(request):
    """Redirect user to Google OAuth consent screen."""
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
    ]
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
    }
    return redirect(f"{base_url}?{urlencode(params)}")


@extend_schema(tags=["Google Drive"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_oauth_callback(request):
    """Exchange auth code for access token and store credentials."""
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Missing code", status=400)

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    token_response = requests.post(token_url, data=data).json()
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")

    google_drive_app = SupportedApp.objects.get(key='google_drive')
    ConnectedApp.objects.update_or_create(
        user=request.user,
        app_id=google_drive_app.id,
        defaults={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": now() + timedelta(seconds=expires_in) if expires_in else None,
            "metadata": token_response,
        },
    )

    # Return HTML response that shows success message and closes the tab after a delay
    html_response = render_to_string("integrations/callback.html")
    
    return HttpResponse(html_response, content_type="text/html")


# ================================
# REVOKE GOOGLE DRIVE ACCESS
# ================================


@extend_schema(
    methods=["POST"],
    tags=["Google Drive"],
    summary="Revoke Google Drive access",
    description="Removes the ConnectedApp record and revokes token from Google.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@csrf_exempt
def revoke_google_drive_access(request):
    """Remove integration and revoke token from Google."""
    try:
        google_drive_app = SupportedApp.objects.get(key='google_drive')
        app = ConnectedApp.objects.get(user=request.user, app_id=google_drive_app.id)
        token = app.access_token

        requests.post(
            "https://oauth2.googleapis.com/revoke",
            params={"token": token},
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=5,
        )

        app.delete()
        return JsonResponse({"success": True})
    except ConnectedApp.DoesNotExist:
        return JsonResponse({"error": "Google Drive not connected"}, status=404)


# ================================
# GOOGLE DRIVE FILE LISTING
# ================================


@extend_schema(tags=["Google Drive"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_google_drive_files(request):
    """List files from user's Google Drive with optional filters."""
    try:
        google_drive_app = SupportedApp.objects.get(key='google_drive')
        creds = ConnectedApp.objects.get(user=request.user, app_id=google_drive_app.id)
        access_token = creds.get_valid_token()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=401)

    # Optional query filters
    mime_type_filter = request.GET.get("mime_type")
    folder_id_filter = request.GET.get("folder_id")
    page_size = int(request.GET.get("page_size", 25))
    page_token = request.GET.get("page_token")

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "pageSize": min(page_size, 1000),
        "fields": "nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, size, owners, iconLink, webViewLink)",
        "spaces": "drive",
    }

    # Build query
    query_parts = []
    if mime_type_filter:
        query_parts.append(f"mimeType='{mime_type_filter}'")
    if folder_id_filter:
        query_parts.append(f"'{folder_id_filter}' in parents")
    if query_parts:
        params["q"] = " and ".join(query_parts)
    if page_token:
        params["pageToken"] = page_token

    try:
        response = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            headers=headers,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        return JsonResponse(
            {
                "files": data.get("files", []),
                "nextPageToken": data.get("nextPageToken"),
            }
        )

    except requests.RequestException as e:
        return JsonResponse({"error": "Google Drive API request failed", "details": str(e)}, status=502)


# ================================
# GOOGLE DRIVE UPLOAD
# ================================


@extend_schema(tags=["Google Drive"])
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@csrf_exempt
def upload_file_to_google_drive(request):
    """Upload a file to user's Google Drive."""
    file: UploadedFile = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    try:
        google_drive_app = SupportedApp.objects.get(key='google_drive')
        creds = ConnectedApp.objects.get(user=request.user, app_id=google_drive_app.id)
        access_token = creds.get_valid_token()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=401)

    metadata = {"name": file.name}
    files = {
        "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
        "file": (file.name, file.file, file.content_type),
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        res = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers=headers,
            files=files,
            timeout=30,
        )
        res.raise_for_status()
        return JsonResponse(res.json())
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to upload to Google Drive", "details": str(e)}, status=502)


# ================================
# GOOGLE DRIVE DOWNLOAD
# ================================


@extend_schema(tags=["Google Drive"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_file_from_google_drive(request, file_id):
    """Download a file from Google Drive by ID."""
    try:
        google_drive_app = SupportedApp.objects.get(key='google_drive')
        creds = ConnectedApp.objects.get(user=request.user, app_id=google_drive_app.id)
        access_token = creds.get_valid_token()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=401)

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        res = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
            headers=headers,
            stream=True,
            timeout=30,
        )
        res.raise_for_status()
        return StreamingHttpResponse(res.iter_content(chunk_size=8192), content_type=res.headers.get("Content-Type"))
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to download file", "details": str(e)}, status=502)


# ================================
# CREATE GOOGLE DOC FROM MARKDOWN
# ================================


@extend_schema(
    methods=["POST"],
    tags=["Google Drive"],
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "markdown": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["markdown"],
        }
    },
    responses={
        200: {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "doc_url": {"type": "string"},
                "title": {"type": "string"},
            },
        },
        401: {"description": "Unauthorized"},
        400: {"description": "Bad Request"},
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@csrf_exempt
def create_google_doc_from_markdown(request):
    """Create a Google Doc from markdown content."""
    try:
        markdown = request.data.get("markdown")
        title = request.data.get("title", "Untitled AI Output")

        if not markdown:
            return JsonResponse({"error": "Missing markdown content."}, status=400)

        google_drive_app = SupportedApp.objects.get(key='google_drive')
        creds = ConnectedApp.objects.get(user=request.user, app_id=google_drive_app.id)
        access_token = creds.get_valid_token()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Step 1: Create empty Google Doc
    try:
        create_res = requests.post(
            "https://docs.googleapis.com/v1/documents",
            headers=headers,
            json={"title": title},
            timeout=10,
        )
        create_res.raise_for_status()
        doc_id = create_res.json()["documentId"]
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to create Google Doc", "details": str(e)}, status=502)

    # Step 2: Convert markdown → Google Docs requests
    try:
        doc_requests = markdown_to_google_docs_requests(markdown)
    except Exception as e:
        return JsonResponse({"error": "Markdown conversion failed", "details": str(e)}, status=500)

    # Step 3: Apply formatting via batchUpdate
    try:
        update_res = requests.post(
            f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
            headers=headers,
            json={"requests": doc_requests},
            timeout=10,
        )
        update_res.raise_for_status()
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to insert content", "details": str(e)}, status=502)

    return JsonResponse(
        {
            "file_id": doc_id,
            "doc_url": f"https://docs.google.com/document/d/{doc_id}/edit",
            "title": title,
        }
    )
