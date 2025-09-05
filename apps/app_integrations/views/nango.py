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

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_nango_session(request):
    url = f"{settings.NANGO_HOST}/connect/sessions"
    headers = {
        "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
    }

    # payload = {
    #     end_user: {
    #         id: request.user.id,
    #         email: request.user.email,
    #         display_name: request.user.username,
    #     },
    #     allowed_integrations: {}
    # }
    payload = {
        "end_user": {
            "id": "2",
            "email": "admin@mail.com",
            "display_name": "admin",
        },
        "allowed_integrations": ['google-drive']
    }
    print(payload)
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        try:
            json_data = response.json()
            return JsonResponse(json_data)
        except ValueError:
            return JsonResponse({"session_token": response.text})
    else:
        return JsonResponse({"error": response.text}, status=response.status_code)

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