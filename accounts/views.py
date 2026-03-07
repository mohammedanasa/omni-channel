from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view


from .models import Merchant
from .serializers import (
    MerchantSerializer,
    MerchantCreateSerializer,
    MerchantUpdateSerializer,
)
from .permissions import IsMerchantOwner


@extend_schema_view(
    list=extend_schema(tags=["Merchants"]),
    retrieve=extend_schema(tags=["Merchants"]),
    create=extend_schema(tags=["Merchants"]),
    update=extend_schema(tags=["Merchants"]),
    partial_update=extend_schema(tags=["Merchants"]),
    destroy=extend_schema(tags=["Merchants"]),
)
class MerchantViewSet(viewsets.ModelViewSet):
    queryset = Merchant.objects.all()

    def get_queryset(self):
        """
        Return only user's merchants.
        Prevent visibility of other tenants.
        """
        return Merchant.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return MerchantCreateSerializer
        if self.action in ["update", "partial_update"]:
            return MerchantUpdateSerializer
        return MerchantSerializer

    def get_permissions(self):
        """
        Permissions:
        - Create/List → authenticated users
        - Retrieve/Update/Delete → owner only
        """
        if self.action in ["retrieve", "update", "partial_update", "destroy"]:
            return [IsMerchantOwner()]   # handles ownership + logged in check
        return [IsAuthenticated()]       # For list & create

    def perform_create(self, serializer):
        """
        Auto-assign owner on merchant creation.
        """
        serializer.save(owner=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """
        Delete merchant ➝ drops tenant schema automatically.
        """
        merchant = self.get_object()  # Permissions already checked
        merchant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)