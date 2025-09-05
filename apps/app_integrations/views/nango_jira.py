from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import requests
import json
from ..models import NangoIntegration
from ..serializers import NangoIntegrationSerializer

@api_view(["POST"])
@permission_classes([AllowAny])
def create_jira_issue(request):
    print("create_jira_issue")
    provider = "jira"
    nango_integration = NangoIntegration.objects.get(user_id=3, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]

    url = f"{settings.NANGO_HOST}/proxy/issue"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': provider,
        'Accept': 'application/json'
    }

    issue = {
        "content" : "Automated issue"
    }
    try:
        response = requests.post(url, json=issue, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to get user list", "details": str(e)}, status=response.status_code)

@api_view(["GET"])
@permission_classes([AllowAny])
def list_jira_user(request):
    print("list_jira_user")
    provider = "jira"
    nango_integration = NangoIntegration.objects.get(user_id=3, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]

    print(connectionId)

    url = f"{settings.NANGO_HOST}/proxy/users/search"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        'Connection-Id': connectionId,
        'Provider-Config-Key': provider,
        'Accept': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return JsonResponse(response.json(), status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": "Failed to get user list", "details": str(e)}, status=response.status_code)