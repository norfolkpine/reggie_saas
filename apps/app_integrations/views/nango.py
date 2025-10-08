from django.http import JsonResponse
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
@permission_classes([IsAuthenticated])
def get_nango_session(request):
    """
    Create a Nango session token for the Connect UI.
    This endpoint creates a session that allows the frontend to initialize the Connect UI.
    Based on: https://docs.nango.dev/reference/api/connect/sessions/create
    """
    url = f"{settings.NANGO_HOST}/connect/sessions"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    # Get the requested integration from the request
    requested_integration = request.data.get('integration') or request.data.get('provider')
    allowed_integrations = request.data.get('allowed_integrations', [])
    
    # If no specific integrations are provided, allow all available integrations
    # or use the requested integration if specified
    if not allowed_integrations:
        if requested_integration:
            allowed_integrations = [requested_integration]
        else:
            # Default to common integrations if nothing specified
            allowed_integrations = ['google-drive', 'jira', 'slack', 'google-mail']
    
    print(f"Request data: {request.data}")
    print(f"Requested integration: {requested_integration}")
    print(f"Allowed integrations: {allowed_integrations}")
    print(f"User: {request.user.username} (ID: {request.user.id})")

    # Build payload according to Nango API specification
    payload = {
        "end_user": {
            "id": str(request.user.id),
            "email": request.user.email,
            "display_name": request.user.username or request.user.email,
            "tags": request.data.get('tags', {})
        },
        "allowed_integrations": allowed_integrations,
        "integrations_config_defaults": request.data.get('integrations_config_defaults', {}),
        "overrides": request.data.get('overrides', {})
    }
    
    # Add organization if provided (deprecated but still supported)
    if 'organization' in request.data:
        payload["organization"] = request.data['organization']
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            try:
                json_data = response.json()
                # Extract token from Nango response and return in expected format
                if 'data' in json_data and 'token' in json_data['data']:
                    return JsonResponse({
                        "data": {
                            "token": json_data['data']['token'],
                            "expires_at": json_data['data'].get('expires_at')
                        }
                    })
                else:
                    # Fallback if response structure is different
                    return JsonResponse(json_data)
            except ValueError:
                return JsonResponse({"session_token": response.text})
        else:
            return JsonResponse({"error": response.text}, status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": f"Request failed: {str(e)}"}, status=500)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_nango_session(request):
    
    data = {
        "user_id": request.user.id if request.user.is_authenticated else request.data.get('user_id'),
        "connection_id": request.data.get('connection_id'),
        "provider": request.data.get('providor')
    }
    
    serializer = NangoIntegrationSerializer(data=data)
    if serializer.is_valid():
        nango_integration = serializer.save()
        return Response({
            "id": nango_integration.id,
            "message": "Nango integration saved successfully",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            "error": "Invalid data",
            "details": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_connected_integrations(request):
    connects = NangoIntegration.objects.filter(user_id = request.user.id)
    serializer = NangoIntegrationSerializer(connects, many=True)
    return JsonResponse({"data": serializer.data}, safe=False)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revoke_nango_connection(request):
    provider = request.data
    nango_integration = NangoIntegration.objects.get(user_id=request.user.id, provider=provider)
    serializer = NangoIntegrationSerializer(nango_integration)
    connectionId = serializer.data["connection_id"]
    url = f"{settings.NANGO_HOST}/connection/{connectionId}"
    headers = {"Authorization": f"Bearer {settings.NANGO_SECRET_KEY}"}
    response = requests.delete(url, headers=headers)
    if response.status_code == 200:
        try:
            nango_integration.delete()
            json_data = response.json()
            return JsonResponse(json_data)
        except ValueError:
            return JsonResponse({"success": response.text})
    else:
        return JsonResponse({"error": response.text}, status=response.status_code)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_nango_integration(request):
    provider = request.data.get('provider')
    
    if not provider:
        return Response({
            "error": "Provider is required"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        nango_integration = NangoIntegration.objects.get(
            user_id=request.user.id, 
            provider=provider
        )
        nango_integration.delete()
        return Response({
            "message": f"NangoIntegration for provider '{provider}' deleted successfully"
        }, status=status.HTTP_204_NO_CONTENT)
    except NangoIntegration.DoesNotExist:
        return Response({
            "error": f"NangoIntegration not found for user_id={request.user.id} and provider='{provider}'"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            "error": f"An error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def test_nango_connection(request):
    """
    Test endpoint to check Nango server connectivity and configuration
    """
    base_url = settings.NANGO_HOST
    if not base_url.endswith('/'):
        base_url += '/'
    
    # Test different endpoints to see which one works
    test_endpoints = [
        f"{base_url}health",
        f"{base_url}api/health", 
        f"{base_url}connect/health",
        f"{base_url}integrations"
    ]
    
    results = {}
    for endpoint in test_endpoints:
        try:
            headers = {
                "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
                "Content-Type": "application/json"
            }
            response = requests.get(endpoint, headers=headers, timeout=5)
            results[endpoint] = {
                "status_code": response.status_code,
                "response": response.text[:200] if response.text else "No response body"
            }
        except requests.RequestException as e:
            results[endpoint] = {
                "error": str(e)
            }
    
    return JsonResponse({
        "nango_host": settings.NANGO_HOST,
        "test_results": results
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_nango_integrations(request):
    """
    Get available Nango integrations from the Nango API
    """
    # Check if a specific integration key is requested
    integration_key = request.GET.get('key')
    
    if integration_key:
        # Get specific integration by key
        url = f"{settings.NANGO_HOST}/integrations/{integration_key}"
    else:
        # Get all integrations
        url = f"{settings.NANGO_HOST}/integrations"
    
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            try:
                json_data = response.json()
                return JsonResponse(json_data)
            except ValueError:
                return JsonResponse({"integrations": response.text})
        else:
            return JsonResponse({"error": response.text}, status=response.status_code)
    except requests.RequestException as e:
        return JsonResponse({"error": f"Request failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)