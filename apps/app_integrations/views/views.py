# Create your views here.
from django.db.models import BooleanField, Exists, OuterRef, Value
from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from apps.app_integrations.models import ConnectedApp, SupportedApp
from apps.app_integrations.serializers import SupportedAppSerializer


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema(
    tags=["App Integrations"],
    responses={200: SupportedAppSerializer(many=True)}
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_supported_apps(request):
    """List all supported app integrations."""
    apps = SupportedApp.objects.filter(is_enabled=True)
    serializer = SupportedAppSerializer(apps, many=True)
    return JsonResponse(serializer.data, safe=False)
