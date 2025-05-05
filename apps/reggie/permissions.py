from rest_framework import permissions


class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return obj.is_public or obj.is_global or obj.uploaded_by == request.user
        return obj.uploaded_by == request.user or request.user.is_superuser


class CanIngestFiles(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.has_perm('reggie.can_ingest_files')


class CanManageGlobalFiles(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.has_perm('reggie.can_manage_global_files')


class IsTeamMemberOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        if hasattr(obj, 'team') and obj.team:
            return obj.team.members.filter(id=request.user.id).exists()
        return False


class IsAgentAccessible(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return obj.is_accessible_by_user(request.user)
        return obj.user == request.user or request.user.is_superuser
