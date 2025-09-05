from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import requests
import json
import http.client
from ..models import NangoIntegration
from ..serializers import NangoIntegrationSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_google_drive_files(request):
    provider = "google_drive"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    url = f"{settings.NANGO_HOST}/proxy/drive/v3/files"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-drive"
    }
    response = requests.get(url, headers=headers)

    print(response.json())
    try:
        json_data = response.json()
        return JsonResponse(json_data)
    except ValueError:
        return JsonResponse({"response": response.text})
    
    return JsonResponse({"error": response.text})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_from_google_drive(request):
    print("download_from_google_drive")
    provider = "google_drive"
    file_id = "1f_qGI_LfH31vBmFBbkvNRhvkn-OJ-0Hx"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    url = f"{settings.NANGO_HOST}/proxy/drive/v3/files/{file_id}"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-drive"
    }
    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        return StreamingHttpResponse(response.iter_content(chunk_size=8192), content_type=response.headers.get("Content-Type"))
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to download file", "details": str(e)}, status=502)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_to_google_drive(request):
    print("upload_to_google_drive")
    provider = "google_drive"
    file: UploadedFile = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file uploaded."}, status=400)
    
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    url = f"{settings.NANGO_HOST}/proxy/drive/v3/files/?uploadType=multipart"
    metadata = {"name": file.name}
    files = {
        "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
        "file": (file.name, file.file, file.content_type),
    }
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-drive"
    }
    try:
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        return JsonResponse({"success": "true"})
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to download file", "details": str(e)}, status=502)