import json

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

from apps.app_integrations.models import ConnectedApp
from apps.app_integrations.utils.markdown_to_google_docs import markdown_to_google_docs_requests


@extend_schema(tags=["App Integrations"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_oauth_start(request):
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"

    scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/documents"]
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        # "scope": "https://www.googleapis.com/auth/drive",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
    }
    from urllib.parse import urlencode

    return redirect(f"{base_url}?{urlencode(params)}")


@extend_schema(tags=["App Integrations"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_oauth_callback(request):
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

    ConnectedApp.objects.update_or_create(
        user=request.user,
        app=ConnectedApp.GOOGLE_DRIVE,
        defaults={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": now() + timedelta(seconds=expires_in) if expires_in else None,
            "metadata": token_response,
        },
    )

    return HttpResponse("✅ Google Drive connected.")


# Revoke access
@extend_schema(
    methods=["POST"],
    tags=["Google Drive"],
    summary="Revoke Google Drive access",
    description="Removes the ConnectedApp record and revokes token from Google.",
    responses={
        200: {"type": "object", "properties": {"success": {"type": "boolean"}}},
        404: {"description": "Google Drive not connected"},
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@csrf_exempt
def revoke_google_drive_access(request):
    try:
        app = ConnectedApp.objects.get(user=request.user, app=ConnectedApp.GOOGLE_DRIVE)
        token = app.access_token

        # Optional: revoke token with Google
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


@extend_schema(tags=["App Integrations"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_google_drive_files(request):
    print("✅ list_google_drive_files: view hit")
    print(f"👤 User: {request.user} (authenticated: {request.user.is_authenticated})")

    try:
        creds = ConnectedApp.objects.get(user=request.user, app=ConnectedApp.GOOGLE_DRIVE)
        print("🔐 ConnectedApp found:", creds)
    except ConnectedApp.DoesNotExist:
        print("❌ No ConnectedApp found for user")
        return JsonResponse({"error": "Google Drive is not connected."}, status=400)

    try:
        access_token = creds.get_valid_token()
        print("🔑 Valid access token obtained")
    except Exception as e:
        print("❌ Token refresh failed:", str(e))
        return JsonResponse({"error": "Unable to refresh Google Drive token", "details": str(e)}, status=401)

    # === Filters ===
    mime_type_filter = request.GET.get("mime_type")  # e.g., "application/pdf"
    folder_id_filter = request.GET.get("folder_id")  # e.g., "abc123"
    page_size = int(request.GET.get("page_size", 25))
    page_token = request.GET.get("page_token")

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "pageSize": min(page_size, 1000),
        "fields": (
            "nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, size, owners, iconLink, webViewLink)"
        ),
        "spaces": "drive",
    }

    # Build q filter string
    query_parts = []
    if mime_type_filter:
        query_parts.append(f"mimeType='{mime_type_filter}'")
    if folder_id_filter:
        query_parts.append(f"'{folder_id_filter}' in parents")
    if query_parts:
        params["q"] = " and ".join(query_parts)

    if page_token:
        params["pageToken"] = page_token

    print("📡 Sending request to Google Drive API...")
    print("🔎 Query Params:", params)

    try:
        response = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            headers=headers,
            params=params,
            timeout=10,
        )
        print(f"📬 Google API status: {response.status_code}")
        response.raise_for_status()

        json_data = response.json()
        files = json_data.get("files", [])
        next_page_token = json_data.get("nextPageToken")

        print(f"📁 Returned {len(files)} files. Next page token: {next_page_token}")

        return JsonResponse(
            {
                "files": files,
                "nextPageToken": next_page_token,
            }
        )

    except requests.exceptions.HTTPError:
        print("❌ Google API error:", response.text)
        return JsonResponse(
            {"error": "Failed to fetch files from Google Drive.", "details": response.text}, status=response.status_code
        )

    except requests.exceptions.RequestException as e:
        print("❌ Request exception:", str(e))
        return JsonResponse({"error": "Google Drive API request failed.", "details": str(e)}, status=502)


@extend_schema(tags=["App Integrations"])
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@csrf_exempt
def upload_file_to_google_drive(request):
    file: UploadedFile = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    try:
        creds = ConnectedApp.objects.get(user=request.user, app=ConnectedApp.GOOGLE_DRIVE)
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


@extend_schema(tags=["App Integrations"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_file_from_google_drive(request, file_id):
    try:
        creds = ConnectedApp.objects.get(user=request.user, app=ConnectedApp.GOOGLE_DRIVE)
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
@extend_schema(tags=["App Integrations"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_oauth_start(request):
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/documents"]
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
    }
    from urllib.parse import urlencode

    return redirect(f"{base_url}?{urlencode(params)}")


@extend_schema(tags=["App Integrations"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_oauth_callback(request):
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

    ConnectedApp.objects.update_or_create(
        user=request.user,
        app=ConnectedApp.GOOGLE_DRIVE,
        defaults={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": now() + timedelta(seconds=expires_in) if expires_in else None,
            "metadata": token_response,
        },
    )

    return HttpResponse("✅ Google Drive connected.")


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
    try:
        markdown = request.data.get("markdown")
        title = request.data.get("title", "Untitled AI Output")

        if not markdown:
            return JsonResponse({"error": "Missing markdown content."}, status=400)

        creds = ConnectedApp.objects.get(user=request.user, app=ConnectedApp.GOOGLE_DRIVE)
        access_token = creds.get_valid_token()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=401)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Step 1: Create the blank document
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

    # Step 2: Convert markdown → Google Docs `requests`
    try:
        doc_requests = markdown_to_google_docs_requests(markdown)
        batch_body = {"requests": doc_requests}
    except Exception as e:
        return JsonResponse({"error": "Markdown conversion failed", "details": str(e)}, status=500)

    # Step 3: Upload content via batchUpdate
    try:
        update_res = requests.post(
            f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
            headers=headers,
            json=batch_body,
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
