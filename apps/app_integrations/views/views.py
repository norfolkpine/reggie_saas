# Create your views here.
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.app_integrations.models import ConnectedApp


@extend_schema(tags=["Connected Apps"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_supported_apps(request):
    """
    Return the list of supported apps for integrations.
    """
    supported_apps = [{"key": key, "label": label} for key, label in ConnectedApp.APP_CHOICES]
    return Response(supported_apps)
