"""
Nango integration views for handling OAuth flows and connection management.
"""

import json
import logging
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.app_integrations.models import ConnectedApp, SupportedApp
from apps.app_integrations.services import get_nango_service

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_nango_auth(request):
    """
    Initiate OAuth flow through Nango.
    
    Expected payload:
    {
        "provider": "google-drive",  // The provider key
        "redirect_uri": "https://yourapp.com/integrations/callback"  // Optional
    }
    """
    provider = request.data.get('provider')
    redirect_uri = request.data.get('redirect_uri')
    
    if not provider:
        return Response(
            {"error": "Provider is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get or create the supported app
    try:
        app = SupportedApp.objects.get(key=provider)
    except SupportedApp.DoesNotExist:
        return Response(
            {"error": f"Provider {provider} not supported"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Generate a unique connection ID for this user and provider
    connection_id = f"user_{request.user.id}_{provider}"
    
    # Get Nango service
    nango = get_nango_service()
    
    # Generate the authorization URL
    auth_url = nango.get_auth_url(
        provider_config_key=provider,
        connection_id=connection_id,
        redirect_uri=redirect_uri or request.build_absolute_uri(reverse('app_integrations:nango_callback')),
        metadata={
            "user_id": str(request.user.id),
            "user_email": request.user.email
        }
    )
    
    return Response({
        "auth_url": auth_url,
        "connection_id": connection_id
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def nango_callback(request):
    """
    Handle OAuth callback from Nango.
    
    Nango will redirect here after successful authentication.
    """
    connection_id = request.GET.get('connectionId')
    provider_config_key = request.GET.get('providerConfigKey')
    
    if not connection_id or not provider_config_key:
        return Response(
            {"error": "Missing connection information"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get the app
    try:
        app = SupportedApp.objects.get(key=provider_config_key)
    except SupportedApp.DoesNotExist:
        return Response(
            {"error": f"Provider {provider_config_key} not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Create or update the connected app
    connected_app, created = ConnectedApp.objects.update_or_create(
        user=request.user,
        app=app,
        defaults={
            "nango_connection_id": connection_id,
            "use_nango": True,
            "metadata": {
                "connected_via": "nango",
                "connection_id": connection_id
            }
        }
    )
    
    action = "connected" if created else "updated"
    
    # Redirect to success page or return JSON
    if request.META.get('HTTP_ACCEPT', '').startswith('application/json'):
        return Response({
            "status": "success",
            "action": action,
            "provider": provider_config_key,
            "connection_id": connection_id
        })
    else:
        # Redirect to a success page
        return HttpResponseRedirect(f"/integrations/success?provider={provider_config_key}")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_connections(request):
    """
    List all Nango connections for the current user.
    """
    connections = ConnectedApp.objects.filter(
        user=request.user,
        use_nango=True
    ).select_related('app')
    
    nango = get_nango_service()
    
    connection_data = []
    for conn in connections:
        # Get connection status from Nango
        nango_conn = nango.get_connection(
            connection_id=conn.nango_connection_id,
            provider_config_key=conn.app.key
        )
        
        connection_data.append({
            "id": conn.id,
            "provider": conn.app.key,
            "provider_name": conn.app.title,
            "connection_id": conn.nango_connection_id,
            "created_at": conn.created_at.isoformat(),
            "status": "connected" if nango_conn else "disconnected",
            "metadata": conn.metadata
        })
    
    return Response(connection_data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def disconnect_integration(request, connection_id):
    """
    Disconnect a Nango integration.
    """
    connected_app = get_object_or_404(
        ConnectedApp,
        id=connection_id,
        user=request.user
    )
    
    if connected_app.use_nango and connected_app.nango_connection_id:
        # Delete from Nango
        nango = get_nango_service()
        nango.delete_connection(
            connection_id=connected_app.nango_connection_id,
            provider_config_key=connected_app.app.key
        )
    
    # Delete from database
    connected_app.delete()
    
    return Response({
        "status": "success",
        "message": f"Disconnected from {connected_app.app.title}"
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_connection(request, connection_id):
    """
    Trigger a sync for a Nango connection (if supported by the provider).
    """
    connected_app = get_object_or_404(
        ConnectedApp,
        id=connection_id,
        user=request.user
    )
    
    if not connected_app.use_nango or not connected_app.nango_connection_id:
        return Response(
            {"error": "This connection does not use Nango"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    nango = get_nango_service()
    success = nango.sync_connection(
        connection_id=connected_app.nango_connection_id,
        provider_config_key=connected_app.app.key
    )
    
    if success:
        return Response({
            "status": "success",
            "message": f"Sync triggered for {connected_app.app.title}"
        })
    else:
        return Response(
            {"error": "Failed to trigger sync"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def proxy_api_request(request):
    """
    Proxy an API request through Nango.
    
    Expected payload:
    {
        "connection_id": 123,
        "method": "GET",
        "endpoint": "/drive/v3/files",
        "params": {...},
        "data": {...}
    }
    """
    connection_id = request.data.get('connection_id')
    method = request.data.get('method', 'GET')
    endpoint = request.data.get('endpoint')
    
    if not connection_id or not endpoint:
        return Response(
            {"error": "connection_id and endpoint are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get the connected app
    connected_app = get_object_or_404(
        ConnectedApp,
        id=connection_id,
        user=request.user
    )
    
    if not connected_app.use_nango:
        return Response(
            {"error": "This connection does not use Nango"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Make the request through the ConnectedApp model
        result = connected_app.make_api_request(
            method=method,
            endpoint=endpoint,
            params=request.data.get('params'),
            json=request.data.get('data')
        )
        
        return Response(result)
    except Exception as e:
        logger.error(f"API proxy request failed: {e}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )