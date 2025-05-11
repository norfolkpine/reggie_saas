from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import HasUserAPIKey

app_name = "api"


@api_view(["GET"])
@permission_classes([HasUserAPIKey])
def health(request):
    """Health check endpoint that requires API key authentication."""
    return Response({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
] 