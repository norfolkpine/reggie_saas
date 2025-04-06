from rest_framework import permissions


class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return obj.is_public or obj.is_global or obj.uploaded_by == request.user
        return obj.uploaded_by == request.user or request.user.is_superuser
