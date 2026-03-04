from rest_framework.permissions import BasePermission

class HasTenantAccess(BasePermission):
    """
    Ensures the tenant from header belongs to the authenticated user.
    """

    def has_permission(self, request, view):
        tenant = getattr(request, "tenant", None)

        # Public routes (no header) allowed only for endpoints that expect it
        if not tenant:
            return False  # Location APIs must have a tenant

        return tenant.owner == request.user
