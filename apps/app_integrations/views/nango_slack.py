from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import requests
import json
from ..models import NangoIntegration
from ..serializers import NangoIntegrationSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def slack_users_list(request):
    print("slack_users_list")
    provider = "slack"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]

    url = f"{settings.NANGO_HOST}/proxy/users.list"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': provider,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to get user list", "details": str(e)}, status=response.status_code)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_slack_user(request):
    print("get_slack_user")
    provider = "slack"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    user = request.data["user"]

    url = f"{settings.NANGO_HOST}/proxy/users.info?user={user}"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': provider,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to get a user from your workspace", "details": str(e)}, status=response.status_code)
    
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def post_slack_message(request):
    print("post_slack_message")
    provider = "slack"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    channel = request.data["channel"]
    message = request.data["message"]

    url = f"{settings.NANGO_HOST}/proxy/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': provider,
        'Content-Type': 'application/json'
    }

    message = {
        "channel": channel,
        "text": message
    }

    try:
        response = requests.post(url, json=message, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to get a user from your workspace", "details": str(e)}, status=response.status_code)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_slack_message(request):
    print("update_slack_message")
    provider = "slack"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    channel = request.data["channel"]
    message = request.data["message"]
    ts = request.data["ts"]

    url = f"{settings.NANGO_HOST}/proxy/chat.update"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': provider,
        'Content-Type': 'application/json'
    }

    update_message = {
        "channel": channel,
        "ts": ts,
        "text": message
    }

    try:
        response = requests.post(url, json=update_message, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to get a user from your workspace", "details": str(e)}, status=response.status_code)   

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def delete_slack_message(request):
    print("delete_slack_message")
    provider = "slack"
    user_id = request.user.id
    nango_integration = NangoIntegration.objects.get(user_id=user_id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    channel = request.data["channel"]
    ts = request.data["ts"]

    url = f"{settings.NANGO_HOST}/proxy/chat.delete"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': provider,
        'Content-Type': 'application/json'
    }

    delete_message = {
        "channel": channel,
        "ts": ts
    }

    try:
        response = requests.post(url, json=delete_message, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to delete your message", "details": str(e)}, status=response.status_code)