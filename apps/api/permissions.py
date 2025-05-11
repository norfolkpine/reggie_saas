import typing

from django.http import HttpRequest
from rest_framework.permissions import IsAuthenticated
from rest_framework_api_key.permissions import BaseHasAPIKey
from rest_framework.exceptions import PermissionDenied

from .helpers import get_user_from_request
from .models import UserAPIKey


class HasUserAPIKey(BaseHasAPIKey):
    model = UserAPIKey

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        has_perm = super().has_permission(request, view)
        if has_perm:
            # if they have permission, also populate the request.user object for convenience
            request.user = get_user_from_request(request)
        return has_perm

    def authenticate_header(self, request):
        return 'Api-Key'

    def permission_denied(self, request, message=None, code=None):
        """
        Override to always return 403 Forbidden instead of 401 Unauthorized
        """
        raise PermissionDenied(detail=message, code=code)


# hybrid permission class that can check for API keys or authentication
IsAuthenticatedOrHasUserAPIKey = IsAuthenticated | HasUserAPIKey
