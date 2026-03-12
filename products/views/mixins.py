import uuid as _uuid

from rest_framework.response import Response
from rest_framework import status

from common.constants import INTERNAL_POS_SLUG
from locations.models import Location


class HeaderContextMixin:
    """Extracts X-Location-ID, X-Channel, and X-Channel-Link-ID from request headers."""

    def _get_location_from_header(self):
        location_id = self.request.META.get('HTTP_X_LOCATION_ID')
        if location_id:
            try:
                _uuid.UUID(str(location_id))
            except ValueError:
                return None
            try:
                return Location.objects.get(id=location_id)
            except Location.DoesNotExist:
                return None
        return None

    def _get_channel_from_header(self):
        channel = self.request.META.get('HTTP_X_CHANNEL')
        return channel.lower() if channel else None

    def _get_channel_link_from_header(self):
        link_id = self.request.META.get('HTTP_X_CHANNEL_LINK_ID')
        if link_id:
            try:
                _uuid.UUID(str(link_id))
            except ValueError:
                return None
            from integrations.models import ChannelLink
            try:
                return ChannelLink.objects.select_related('channel').get(id=link_id)
            except ChannelLink.DoesNotExist:
                return None
        return None


class CatalogWriteProtectionMixin:
    """
    Blocks writes to POS-owned fields based on per-product ownership (Product.managed_by).

    - Products with managed_by="internal_pos" (local/platform-owned) are fully writable.
    - Products with managed_by="clover" (or any external POS slug) have core fields read-only.
    - Product creation is always allowed (new products default to managed_by="internal_pos").
    - Override layers (location pricing, availability, menu curation) are always writable.
    """

    # Core catalog fields that the POS owns
    POS_PROTECTED_FIELDS = frozenset({
        "name", "description", "price", "plu", "pos_product_id", "gtin",
        "product_type", "category", "categories", "image_url",
        "kitchen_name", "name_translations", "description_translations",
        "is_combo", "is_variant", "is_variant_group",
        "delivery_tax_rate", "takeaway_tax_rate", "eat_in_tax_rate",
        "min_select", "max_select", "multi_max", "max_free",
        "default_quantity", "sort_order", "sub_products",
        "calories", "calories_range_high", "nutritional_info",
        "beverage_info", "packaging", "product_tags",
    })

    # Actions that are always allowed (override layers, not catalog data)
    WRITE_EXEMPT_ACTIONS = frozenset({
        "update_location_pricing", "mark_unavailable",
    })

    def _check_write_protection(self, request, product=None):
        """
        Returns a 403 Response if the request tries to modify POS-owned fields
        on a POS-managed product, or None if the write is allowed.

        Args:
            request: The DRF request.
            product: The Product instance being modified (None for create/list actions).
        """
        # Check if current action is exempt
        action_name = getattr(self, 'action', None)
        if action_name in self.WRITE_EXEMPT_ACTIONS:
            return None

        # Product creation is always allowed — new products default to internal_pos
        if request.method == "POST" and action_name == "create":
            return None

        # For detail actions (update/delete), check the product's managed_by
        if product is None:
            return None

        managed_by = getattr(product, 'managed_by', INTERNAL_POS_SLUG)
        if not managed_by or managed_by == INTERNAL_POS_SLUG:
            return None  # Platform-owned product — fully writable

        # Block delete on POS-managed products
        if request.method == "DELETE":
            return Response(
                {
                    "error": f"This product is managed by {managed_by}. "
                    f"Remove it from {managed_by} and re-sync via pull_menu."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # For PATCH/PUT, check which fields are being modified
        if request.method in ("PUT", "PATCH") and action_name in ("update", "partial_update"):
            protected = set(request.data.keys()) & self.POS_PROTECTED_FIELDS
            if protected:
                return Response(
                    {
                        "error": f"These fields are managed by {managed_by}: "
                        f"{', '.join(sorted(protected))}. "
                        f"Update them in {managed_by} and use pull_menu to sync."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        return None

    def update(self, request, *args, **kwargs):
        product = self.get_object()
        error = self._check_write_protection(request, product=product)
        if error:
            return error
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        product = self.get_object()
        error = self._check_write_protection(request, product=product)
        if error:
            return error
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        error = self._check_write_protection(request, product=product)
        if error:
            return error
        return super().destroy(request, *args, **kwargs)
