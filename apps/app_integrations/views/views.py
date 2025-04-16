# Create your views here.
from django.db.models import BooleanField, Exists, OuterRef, Value
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
def list_supported_apps(request):
    """
    Return the paginated list of supported apps for integrations.
    For authenticated users, includes whether each app is connected.
    For unauthenticated users, simply returns the list of supported apps.
    """
    # Base queryset to get all supported apps
    queryset = SupportedApp.objects.all()
    
    # Check if user is authenticated
    if request.user and request.user.is_authenticated:
        # For authenticated users, annotate with connection status
        queryset = queryset.annotate(
            is_connected=Exists(ConnectedApp.objects.filter(user=request.user, app_id=OuterRef("pk")))
        )
    else:
        # For unauthenticated users, set is_connected to False for all apps
        queryset = queryset.annotate(
            is_connected=Value(False, output_field=BooleanField())
        )
    
    # Select only the fields we need
    queryset = queryset.values("key", "title", "description", "icon_url", "is_connected")
    
    # Paginate the results
    paginator = StandardResultsSetPagination()
    result_page = paginator.paginate_queryset(queryset, request)
    
    return paginator.get_paginated_response(result_page)
