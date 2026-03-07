from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from ..models import Category
from ..serializers import CategorySerializer
from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema, LOCATION_HEADER
from .mixins import HeaderContextMixin


@tenant_schema("Categories", LOCATION_HEADER)
class CategoryViewSet(HeaderContextMixin, viewsets.ModelViewSet):
    """Category management viewset. Lookup by pos_category_id."""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]
    lookup_field = 'pos_category_id'

    def get_queryset(self):
        queryset = Category.objects.all()

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(pos_category_id__icontains=search)
            )

        location = self._get_location_from_header()
        is_available = self.request.query_params.get('is_available')

        if is_available == 'true' and location:
            queryset = queryset.filter(
                products__location_links__location=location,
                products__location_links__is_available=True,
            ).distinct()

        return queryset.order_by('sort_order', 'name')
