from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema
from integrations.adapters import AdapterRegistry
from integrations.canonical.menu import CanonicalMenu
from .models import ChannelLink, ProductChannelConfig, SyncStatus
from .serializers import ChannelLinkSerializer, ProductChannelConfigSerializer
from .services import IntegrationSyncService


@tenant_schema("Channel Links")
class ChannelLinkViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelLinkSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]

    def get_queryset(self):
        return ChannelLink.objects.select_related("channel", "location").all()

    @extend_schema(tags=["Channel Links"], request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        """Validate credentials for this channel link."""
        link = self.get_object()
        adapter = AdapterRegistry.get_adapter(link)
        is_valid = adapter.validate_credentials()
        return Response({"valid": is_valid})

    @extend_schema(tags=["Channel Links"], request=None, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="sync_menu")
    def sync_menu(self, request, pk=None):
        """Push the current menu to the linked channel."""
        link = self.get_object()
        adapter = AdapterRegistry.get_adapter(link)

        link.sync_status = SyncStatus.SYNCING
        link.save(update_fields=["sync_status"])

        try:
            from products.models import Product

            qs = Product.objects.filter(locations__location=link.location).distinct()
            menu = CanonicalMenu.from_product_queryset(
                qs, link.location, channel_slug=link.channel.slug
            )
            result = adapter.push_menu(menu)

            link.sync_status = SyncStatus.SYNCED if result.success else SyncStatus.ERROR
            link.sync_error = "" if result.success else result.message
            link.last_sync_at = timezone.now()
            link.save(update_fields=["sync_status", "sync_error", "last_sync_at"])

            return Response(result.to_dict(), status=status.HTTP_200_OK)

        except Exception as e:
            link.sync_status = SyncStatus.ERROR
            link.sync_error = str(e)
            link.save(update_fields=["sync_status", "sync_error"])
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(tags=["Channel Links"], request=None, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="pull_menu")
    def pull_menu(self, request, pk=None):
        """
        Pull menu from external channel and persist into local products.

        Calls adapter.pull_menu() → converts CanonicalMenu → upserts
        products, categories, and modifiers. Also assigns products to
        the channel link's location with channel-specific pricing.
        """
        link = self.get_object()

        if not link.channel.adapter_class:
            return Response(
                {"success": False, "message": "No adapter configured for this channel."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = IntegrationSyncService.pull_and_persist(link)
        return Response(
            result.to_dict(),
            status=status.HTTP_200_OK if result.success else status.HTTP_400_BAD_REQUEST,
        )


@tenant_schema("Product Channel Config")
class ProductChannelConfigViewSet(viewsets.ModelViewSet):
    serializer_class = ProductChannelConfigSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]

    def get_queryset(self):
        return ProductChannelConfig.objects.select_related(
            "channel", "product_location"
        ).all()
