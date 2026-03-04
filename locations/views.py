from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from helpers.permissions.permissions import HasTenantAccess

from .models import Location
from .serializers import LocationSerializer
from accounts.permissions import IsMerchantOwner
from helpers.common import tenant_schema

@tenant_schema("Locations")
class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer

    def get_queryset(self):
        return Location.objects.all()  # Tenant schema already switched

    def get_permissions(self):
        # Only merchant owner can access tenant resources
        return [IsAuthenticated(), HasTenantAccess()]

    
