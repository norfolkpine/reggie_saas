from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import HasUserAPIKey
from .test_views import test_dual_auth, test_jwt_only

app_name = "api"


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()


@extend_schema(
    responses=HealthSerializer,
    summary="Health check endpoint",
    description="A simple GET endpoint that verifies the service is up. Requires a valid API key.",
)
@api_view(["GET"])
@permission_classes([HasUserAPIKey])
def health(request):
    """Health check endpoint that requires API key authentication."""
    return Response({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
    path("test-dual-auth/", test_dual_auth, name="test_dual_auth"),
    path("test-jwt-only/", test_jwt_only, name="test_jwt_only"),
]
