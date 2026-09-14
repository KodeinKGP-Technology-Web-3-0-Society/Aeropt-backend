from django.conf import settings
from rest_framework.permissions import BasePermission, IsAuthenticated


class IsOwner(BasePermission):
    """Object-level permission: user can only access their own resources."""

    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, self.owner_field, None)
        if owner is None:
            return False
        owner_id = owner.id if hasattr(owner, "id") else owner
        return owner_id == request.user.id


class IsOwnerOrAdmin(BasePermission):
    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        owner = getattr(obj, self.owner_field, None)
        if owner is None:
            return False
        owner_id = owner.id if hasattr(owner, "id") else owner
        return owner_id == request.user.id


def get_default_permission_classes():
    if getattr(settings, "DEV_AUTH_BYPASS", False):
        from rest_framework.permissions import AllowAny

        return [AllowAny]
    return [IsAuthenticated]
