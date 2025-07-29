from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .permissions import IsAuthenticatedOrHasUserAPIKey


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrHasUserAPIKey])
def test_dual_auth(request):
    """
    Test endpoint that demonstrates both JWT/session and API key authentication work.
    
    This endpoint can be accessed via:
    1. JWT token in Authorization header: Bearer <token>
    2. Session authentication (cookies)
    3. API key in Authorization header: Api-Key <key>
    """
    return Response({
        "message": "Authentication successful!",
        "user_id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        "auth_type": "JWT/Session" if request.user.is_authenticated else "API Key",
        "permissions": list(request.user.get_all_permissions()),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_jwt_only(request):
    """
    Test endpoint that only accepts JWT/session authentication.
    
    This endpoint can be accessed via:
    1. JWT token in Authorization header: Bearer <token>
    2. Session authentication (cookies)
    
    API keys will be rejected.
    """
    return Response({
        "message": "JWT/Session authentication successful!",
        "user_id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        "auth_type": "JWT/Session",
    }, status=status.HTTP_200_OK) 