# from django.utils.deprecation import MiddlewareMixin
# from django.db import connection
# from django_tenants.utils import get_tenant_model
# from django.core.exceptions import PermissionDenied

# class TenantFromHeaderMiddleware(MiddlewareMixin):
#     """
#     Switch tenant schema using X-Tenant-ID header.
#     """

#     def process_request(self, request):
#         tenant_id = request.headers.get("X-Tenant-ID")

#         # No tenant -> use public schema
#         if not tenant_id:
#             connection.set_schema_to_public()
#             return

#         TenantModel = get_tenant_model()

#         try:
#             tenant = TenantModel.objects.get(id=tenant_id)
#         except TenantModel.DoesNotExist:
#             raise PermissionDenied("Invalid Tenant ID")

#         request.tenant = tenant
#         connection.set_tenant(tenant)   # <<< REQUIRED LINE

#         print(f"✔ Tenant switched → {tenant.schema_name}")

#     def process_response(self, request, response):
#         connection.set_schema_to_public()
#         return response


import uuid as _uuid

from django.db import connection
from django.http import JsonResponse
from django_tenants.utils import get_tenant_model

class TenantFromHeaderMiddleware:
    # URL prefixes that require a tenant schema (i.e. TENANT_APPS).
    # Requests to these paths without X-Tenant-ID will be rejected early.
    TENANT_ONLY_PREFIXES = [
        "/api/v1/products/",
        "/api/v1/categories/",
        "/api/v1/tax-rates/",
        "/api/v1/locations/",
        "/api/v1/channel-links/",
        "/api/v1/product-channel-configs/",
        "/api/v1/orders/",
        "/api/v1/webhooks/endpoints/",
        "/api/v1/webhooks/logs/",
    ]

    # Paths that resolve tenant themselves (e.g. from ChannelLink UUID)
    TENANT_EXEMPT_PREFIXES = [
        "/api/v1/webhooks/inbound/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def _requires_tenant(self, path):
        """Check if the request path belongs to a tenant-only app."""
        if any(path.startswith(prefix) for prefix in self.TENANT_EXEMPT_PREFIXES):
            return False
        return any(path.startswith(prefix) for prefix in self.TENANT_ONLY_PREFIXES)

    def __call__(self, request):

        tenant_id = request.headers.get("X-Tenant-ID")

        if tenant_id:
            # Validate UUID format before hitting the DB
            try:
                _uuid.UUID(str(tenant_id))
            except ValueError:
                return JsonResponse(
                    {"error": f"'{tenant_id}' is not a valid UUID. Pass a real Merchant UUID."},
                    status=400,
                )

            Tenant = get_tenant_model()
            try:
                tenant = Tenant.objects.get(id=tenant_id)
                connection.set_tenant(tenant)
                request.tenant = tenant
                print(f"✔ ACTIVE TENANT → {tenant.schema_name}")
            except Tenant.DoesNotExist:
                return JsonResponse({"error": "Invalid tenant"}, status=400)

        else:
            # Block tenant-only endpoints that would crash on the public schema
            if self._requires_tenant(request.path):
                return JsonResponse(
                    {"error": "X-Tenant-ID header is required for this endpoint."},
                    status=400,
                )

            print("→ No tenant passed → using PUBLIC schema")
            connection.set_schema_to_public()

        response = self.get_response(request)
        connection.set_schema_to_public()   # reset after response
        return response
