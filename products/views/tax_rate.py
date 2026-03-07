from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ..models import TaxRate
from ..serializers import TaxRateSerializer
from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema, LOCATION_HEADER


@tenant_schema("Tax Rates", LOCATION_HEADER)
class TaxRateViewSet(viewsets.ModelViewSet):
    """Tax rate management viewset."""

    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]

    def get_queryset(self):
        queryset = TaxRate.objects.all()

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        is_default = self.request.query_params.get('is_default')
        if is_default is not None:
            queryset = queryset.filter(is_default=is_default.lower() == 'true')

        return queryset.order_by('-is_default', 'name')
