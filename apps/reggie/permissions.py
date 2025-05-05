import logging

from rest_framework import permissions
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_api_key.permissions import BaseHasAPIKey

from apps.api.models import UserAPIKey
from apps.api.permissions import HasUserAPIKey

logger = logging.getLogger(__name__)


class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return obj.is_public or obj.is_global or obj.uploaded_by == request.user
        return obj.uploaded_by == request.user or request.user.is_superuser


class CanIngestFiles(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.has_perm("reggie.can_ingest_files")


class CanManageGlobalFiles(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.has_perm("reggie.can_manage_global_files")


class IsTeamMemberOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        if hasattr(obj, "team") and obj.team:
            return obj.team.members.filter(id=request.user.id).exists()
        return False


class IsAgentAccessible(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return obj.is_accessible_by_user(request.user)
        return obj.user == request.user or request.user.is_superuser


class HasValidSystemAPIKey(BaseHasAPIKey):
    """
    Permission class for system-to-system API authentication.
    Used for services like Cloud Run that need to communicate with the Django backend.
    """

    model = UserAPIKey

    def has_permission(self, request, view):
        try:
            auth_header = request.headers.get("Authorization", "")
            logger.info(f"🔑 Validating system API key auth header: {auth_header[:15]}...")

            if not auth_header.startswith("Api-Key "):
                logger.error("❌ Invalid API key format - must start with 'Api-Key '")
                return False

            # Get the API key from the request
            key = self.get_key(request)
            if not key:
                logger.error("❌ No API key found in request")
                return False

            # Get the API key from the database
            api_key = self.model.objects.get_from_key(key)
            if not api_key.user.email.endswith("@system.local"):
                logger.error(f"❌ API key belongs to non-system user: {api_key.user.email}")
                return False

            # Validate the key
            if not self.model.objects.is_valid(key):
                logger.error("❌ API key is invalid or revoked")
                return False

            logger.info("✅ System API key validation successful")
            return True

        except Exception as e:
            logger.error(f"❌ System API key validation failed: {str(e)}")
            return False


class HasValidUserAPIKey(HasUserAPIKey):
    """
    Permission class for user-specific API key authentication.
    Used when individual users or teams need API access to specific resources.
    """

    def has_permission(self, request, view):
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Api-Key "):
                raise AuthenticationFailed('Invalid API key format. Must start with "Api-Key "')
            return super().has_permission(request, view)
        except Exception as e:
            raise AuthenticationFailed(f"User API key validation failed: {str(e)}")


# Composite permissions for common use cases
class HasSystemOrUserAPIKey(permissions.BasePermission):
    """
    Permission class that allows either system API keys or user API keys.
    Useful for endpoints that can be accessed by both systems and users with API keys.
    """

    def has_permission(self, request, view):
        system_perm = HasValidSystemAPIKey()
        user_perm = HasValidUserAPIKey()

        return system_perm.has_permission(request, view) or user_perm.has_permission(request, view)
