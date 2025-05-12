from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import serializers

from drf_spectacular.utils import extend_schema

from .permissions import HasUserAPIKey

app_name = "api"


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()


@extend_schema(
    responses=HealthSerializer,
    summary="Health check endpoint",
    description="A simple GET endpoint that verifies the service is up. Requires a valid API key."
)
@api_view(["GET"])
@permission_classes([HasUserAPIKey])
def health(request):
    """Health check endpoint that requires API key authentication."""
    return Response({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
]
