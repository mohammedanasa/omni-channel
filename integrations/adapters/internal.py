from __future__ import annotations

from integrations.adapters.base import AbstractChannelAdapter
from integrations.canonical.menu import CanonicalMenu
from integrations.canonical.orders import CanonicalOrder
from integrations.canonical.results import SyncResult, WebhookResult


class InternalPOSAdapter(AbstractChannelAdapter):
    """
    Adapter for the internal POS — the database IS the source of truth.
    push_menu / update_order_status are no-ops because there is no external system.
    """

    def push_menu(self, canonical_menu: CanonicalMenu) -> SyncResult:
        return SyncResult(success=True, message="Internal POS: menu is the database.")

    def pull_menu(self) -> CanonicalMenu:
        from products.models import Product

        qs = Product.objects.filter(locations__location=self.location).distinct()
        return CanonicalMenu.from_product_queryset(
            qs, self.location, channel_slug="internal_pos"
        )

    def normalize_inbound_order(self, raw_payload: dict) -> CanonicalOrder:
        return CanonicalOrder.from_dict(raw_payload)

    def update_order_status(
        self, external_order_id: str, status: str, reason: str = ""
    ) -> bool:
        return True  # no external system to notify

    def update_availability(
        self, items: list[dict], available: bool
    ) -> SyncResult:
        from products.models import ProductLocation

        updated = 0
        for item in items:
            plu = item.get("plu")
            if not plu:
                continue
            count = ProductLocation.objects.filter(
                product__plu=plu, location=self.location
            ).update(is_available=available)
            updated += count

        return SyncResult(
            success=True,
            message=f"Updated {updated} product-locations.",
            updated_count=updated,
        )

    def validate_credentials(self) -> bool:
        return True

    def verify_webhook_signature(self, payload: bytes, headers: dict) -> bool:
        return True

    def handle_webhook(
        self, event_type: str, payload: dict, headers: dict
    ) -> WebhookResult:
        # Route menu events to the menu handler
        if event_type.startswith("menu.") or event_type.startswith("item."):
            return self.handle_menu_webhook(event_type, payload, headers)
        return WebhookResult(success=True, action="noop", message="Internal POS: no-op.")

    def handle_menu_webhook(
        self, event_type: str, payload: dict, headers: dict
    ) -> WebhookResult:
        # Internal POS: DB is source of truth, no external menu to pull
        return WebhookResult(
            success=True,
            action="noop",
            message="Internal POS: menu is the database.",
        )
