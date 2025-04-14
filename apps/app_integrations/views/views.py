# Create your views here.
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from apps.app_integrations.models import SupportedApp

@extend_schema(tags=["Connected Apps"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_supported_apps(request):
    """
    Return the list of supported apps for integrations.
    """
    supported_apps = list(SupportedApp.objects.values('key', 'title', 'description', 'icon_url'))
    return Response(supported_apps)
