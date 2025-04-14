# Create your views here.
from django.db.models import Exists, OuterRef
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from apps.app_integrations.models import ConnectedApp, SupportedApp


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema(tags=["Connected Apps"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_supported_apps(request):
    """
    Return the paginated list of supported apps for integrations.
    """
    queryset = SupportedApp.objects.annotate(
        is_connected=Exists(ConnectedApp.objects.filter(user=request.user, app=OuterRef("pk")))
    ).values("key", "title", "description", "icon_url", "is_connected")
    paginator = StandardResultsSetPagination()
    result_page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(result_page)
