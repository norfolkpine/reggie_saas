from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import requests
import json
import base64
from email.message import EmailMessage
from ..models import NangoIntegration
from ..serializers import NangoIntegrationSerializer

@api_view(["POST"])
@permission_classes([AllowAny])
def gmail_create_draft(request):
    print("gmail_create_draft")
    provider = "google-mail"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]

    url = f"{settings.NANGO_HOST}/proxy/gmail/v1/users/me/drafts"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-mail",
        'Content-Type': 'application/json'
    }

    message = EmailMessage()
    message.set_content(request.data["content"])
    message["To"] = request.data["to_email"]
    message["From"] = request.data["from_email"]
    message["Subject"] = request.data["subject"]
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {
        "message": {
            "raw": encoded_message
        }
    }
    
    try:
        response = requests.post(url, json=create_message, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to draft mail", "details": str(e)}, status=response.status_code)

@api_view(["POST"])
@permission_classes([AllowAny])
def gmail_draft_send(request):
    
    print("gmail_draft_send")

    provider = "google-mail"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    
    url = f"{settings.NANGO_HOST}/proxy/gmail/v1/users/me/drafts/send"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-mail",
        'Content-Type': 'application/json'
    }

    create_message = {
        "id": request.data["draft_id"]
    }
    
    try:
        response = requests.post(url, json=create_message, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to draft mail", "details": str(e)}, status=response.status_code)

@api_view(["GET"])
@permission_classes([AllowAny])
def list_draft_mail(request):
    print("list_draft_mail")
    provider = "google-mail"

    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]

    url = f"{settings.NANGO_HOST}/proxy/gmail/v1/users/me/drafts"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-mail",
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to draft mail", "details": str(e)}, status=response.status_code)

@api_view(["POST"])
@permission_classes([AllowAny])
def get_draft_mail(request):
    print("get_draft_mail")
    provider = "google-mail"

    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    draft_id = request.data["draft_id"]

    url = f"{settings.NANGO_HOST}/proxy/gmail/v1/users/me/drafts/{draft_id}"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-mail",
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to draft mail", "details": str(e)}, status=response.status_code)

@api_view(["POST"])
@permission_classes([AllowAny])
def update_draft_mail(request):
    print("update_draft_mail")
    provider = "google-mail"

    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    draft_id = request.data["draft_id"]

    url = f"{settings.NANGO_HOST}/proxy/gmail/v1/users/me/drafts/{draft_id}"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-mail",
        'Content-Type': 'application/json'
    }

    message = EmailMessage()
    message.set_content(request.data["content"])
    message["To"] = request.data["to_email"]
    message["From"] = request.data["from_email"]
    message["Subject"] = request.data["subject"]
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    update_message = {
        "message": {
            "raw": encoded_message
        }
    }

    try:
        response = requests.put(url, json=update_message, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to draft mail", "details": str(e)}, status=response.status_code)


@api_view(["POST"])
@permission_classes([AllowAny])
def delete_draft_mail(request):
    print("delete_draft_mail")
    provider = "google-mail"

    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    draft_id = request.data["draft_id"]

    url = f"{settings.NANGO_HOST}/proxy/gmail/v1/users/me/drafts/{draft_id}"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': "google-mail",
        'Content-Type': 'application/json'
    }

    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to draft mail", "details": str(e)}, status=response.status_code)