"""
Deliveroo Channel Adapter
=========================

Connects to Deliveroo's Partner Platform API for:
- Menu sync (push menu to Deliveroo)
- Order ingestion (normalize inbound webhook orders)
- Order status updates (accept/reject + prep stages)
- Item availability management
- Webhook HMAC-SHA256 verification

Deliveroo API docs: https://api-docs.deliveroo.com

Required credentials (stored in ChannelLink.credentials):
{
    "client_id": "...",
    "client_secret": "...",
    "brand_id": "...",
    "site_id": "...",
    "menu_id": "...",           # assigned after first menu push
    "webhook_secret": "...",    # HMAC secret from Deliveroo Developer Portal
    "environment": "sandbox"    # or "production"
}
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from integrations.adapters.base import AbstractChannelAdapter
from integrations.canonical.menu import (
    CanonicalMenu,
    CanonicalModifier,
    CanonicalModifierGroup,
    CanonicalProduct,
)
from integrations.canonical.orders import (
    CanonicalOrder,
    CanonicalOrderItem,
    CanonicalOrderModifier,
)
from integrations.canonical.results import SyncResult, WebhookResult

logger = logging.getLogger(__name__)

# ── Deliveroo environment URLs ──────────────────────────────────────

ENVIRONMENTS = {
    "sandbox": {
        "auth": "https://auth-sandbox.developers.deliveroo.com",
        "api": "https://api-sandbox.developers.deliveroo.com",
    },
    "production": {
        "auth": "https://auth.developers.deliveroo.com",
        "api": "https://api.developers.deliveroo.com",
    },
}

# ── Status mapping: your system → Deliveroo ─────────────────────────

# Deliveroo only allows accept/reject via PATCH, then prep stages via POST.
# Your internal statuses map to Deliveroo actions, not 1:1 status strings.
PREP_STAGE_MAP = {
    "preparing": "in_kitchen",
    "ready": "ready_for_collection",
    "picked_up": "collected",
}

# Deliveroo fulfillment type → your OrderType
FULFILLMENT_MAP = {
    "DELIVERY": "delivery",
    "PICKUP": "pickup",
    "COLLECTION": "pickup",
}


class DeliverooAdapter(AbstractChannelAdapter):
    """
    Adapter for Deliveroo's Partner Platform API.

    Token lifecycle: Deliveroo OAuth2 tokens expire every 300s (5 min).
    This adapter caches the token in memory and refreshes on expiry.
    """

    _token_cache: dict = {}  # class-level: {client_id: (token, expires_at)}

    def __init__(self, channel_link) -> None:
        super().__init__(channel_link)
        self.client_id = self.credentials.get("client_id", "")
        self.client_secret = self.credentials.get("client_secret", "")
        self.brand_id = self.credentials.get("brand_id", "")
        self.site_id = self.credentials.get("site_id", "")
        self.menu_id = self.credentials.get("menu_id", "")
        self.webhook_secret = self.credentials.get("webhook_secret", "")
        env = self.credentials.get("environment", "sandbox")
        urls = ENVIRONMENTS.get(env, ENVIRONMENTS["sandbox"])
        self.auth_url = urls["auth"]
        self.api_url = urls["api"]

    # ── OAuth2 Token Management ──────────────────────────────────────

    def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if expired."""
        cached = self._token_cache.get(self.client_id)
        if cached:
            token, expires_at = cached
            if time.time() < expires_at - 30:  # 30s buffer
                return token

        resp = requests.post(
            f"{self.auth_url}/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        token = data["access_token"]
        expires_in = data.get("expires_in", 300)
        self._token_cache[self.client_id] = (token, time.time() + expires_in)
        return token

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    # ── Menu Sync ────────────────────────────────────────────────────

    def push_menu(self, canonical_menu: CanonicalMenu) -> SyncResult:
        """Convert CanonicalMenu → Deliveroo menu JSON and upload."""
        deliveroo_menu = self._canonical_to_deliveroo_menu(canonical_menu)

        try:
            resp = requests.put(
                f"{self.api_url}/menu/v2/brands/{self.brand_id}/menus",
                json=deliveroo_menu,
                headers=self._auth_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            result_data = resp.json() if resp.content else {}

            # Store menu_id if returned
            menu_id = result_data.get("menu_id", "")
            if menu_id and menu_id != self.menu_id:
                self.channel_link.credentials["menu_id"] = menu_id
                self.channel_link.save(update_fields=["credentials"])
                self.menu_id = menu_id

            return SyncResult(
                success=True,
                message="Menu pushed to Deliveroo.",
                created_count=len(canonical_menu.products),
            )
        except requests.HTTPError as e:
            error_body = e.response.text if e.response is not None else str(e)
            logger.error("Deliveroo menu push failed: %s", error_body)
            return SyncResult(
                success=False,
                message=f"Deliveroo API error: {e.response.status_code}",
                errors=[error_body],
            )
        except requests.RequestException as e:
            logger.error("Deliveroo menu push connection error: %s", e)
            return SyncResult(success=False, message=str(e), errors=[str(e)])

    def pull_menu(self) -> CanonicalMenu:
        """Pull is not supported by Deliveroo — build from local DB instead."""
        from products.models import Product

        qs = Product.objects.filter(locations__location=self.location).distinct()
        return CanonicalMenu.from_product_queryset(
            qs, self.location, channel_slug="deliveroo"
        )

    def _canonical_to_deliveroo_menu(self, menu: CanonicalMenu) -> dict:
        """Transform CanonicalMenu into Deliveroo's menu upload format."""
        categories = []
        items = []
        modifiers = []

        # Group products by category
        cat_items: dict[str, list[str]] = {}
        for product in menu.products:
            cat = product.category_name or "Uncategorised"
            cat_id = self._slugify(cat)
            cat_items.setdefault(cat_id, [])

            item_id = product.plu
            cat_items[cat_id].append(item_id)

            # Build item
            modifier_ids = []
            for mg in product.modifier_groups:
                mod_id = mg.plu
                modifier_ids.append(mod_id)

                # Modifier group → Deliveroo "modifier"
                choice_ids = []
                for mod in mg.modifiers:
                    choice_id = mod.plu
                    choice_ids.append(choice_id)
                    # Each modifier option is an "item" of type CHOICE
                    items.append({
                        "id": choice_id,
                        "name": {"en": mod.name},
                        "plu": mod.plu,
                        "price_info": {"price": mod.price},
                        "type": "CHOICE",
                    })

                modifiers.append({
                    "id": mod_id,
                    "name": {"en": mg.name},
                    "item_ids": choice_ids,
                    "min_selection": mg.min_select,
                    "max_selection": mg.max_select or len(choice_ids),
                })

            item_payload: dict = {
                "id": item_id,
                "name": {"en": product.name},
                "plu": product.plu,
                "price_info": {"price": product.price},
                "type": "ITEM",
            }
            if product.description:
                item_payload["description"] = {"en": product.description}
            if product.image_url:
                item_payload["image_url"] = product.image_url
            if modifier_ids:
                item_payload["modifier_ids"] = modifier_ids

            items.append(item_payload)

        # Build categories
        for cat_name in menu.categories:
            cat_id = self._slugify(cat_name)
            categories.append({
                "id": cat_id,
                "name": {"en": cat_name},
                "item_ids": cat_items.get(cat_id, []),
            })

        # If there are items with no category, add "Uncategorised"
        uncat = cat_items.get("uncategorised", [])
        if uncat and "uncategorised" not in [c["id"] for c in categories]:
            categories.append({
                "id": "uncategorised",
                "name": {"en": "Uncategorised"},
                "item_ids": uncat,
            })

        return {
            "name": f"menu-{self.site_id}",
            "menu": {
                "categories": categories,
                "items": items,
                "modifiers": modifiers,
            },
            "site_ids": [self.site_id],
        }

    # ── Orders ───────────────────────────────────────────────────────

    def normalize_inbound_order(self, raw_payload: dict) -> CanonicalOrder:
        """Convert a Deliveroo order webhook payload → CanonicalOrder."""
        order_data = raw_payload.get("order", raw_payload)

        items = []
        for d_item in order_data.get("items", []):
            modifiers = []
            for d_mod in d_item.get("modifiers", []):
                for d_opt in d_mod.get("options", [d_mod]):
                    modifiers.append(CanonicalOrderModifier(
                        plu=d_opt.get("plu", d_opt.get("id", "")),
                        name=d_opt.get("name", ""),
                        quantity=d_opt.get("quantity", 1),
                        unit_price=d_opt.get("total_price", {}).get("fractional", 0)
                        if isinstance(d_opt.get("total_price"), dict)
                        else d_opt.get("price", 0),
                        group_name=d_mod.get("name", ""),
                        group_plu=d_mod.get("id", ""),
                    ))

            items.append(CanonicalOrderItem(
                plu=d_item.get("plu", d_item.get("id", "")),
                name=d_item.get("name", ""),
                quantity=d_item.get("quantity", 1),
                unit_price=self._extract_price(d_item, "total_price"),
                notes=d_item.get("notes", ""),
                modifiers=modifiers,
                external_item_id=str(d_item.get("id", "")),
            ))

        # Financials
        price_data = order_data.get("price", {})
        fulfillment = order_data.get("fulfillment", {})
        fulfillment_type = fulfillment.get("type", "DELIVERY")
        customer = order_data.get("customer", {})
        delivery_addr = fulfillment.get("delivery_address", {})

        address_parts = [
            delivery_addr.get("address_line1", ""),
            delivery_addr.get("address_line2", ""),
            delivery_addr.get("city", ""),
            delivery_addr.get("post_code", ""),
        ]
        address_str = ", ".join(p for p in address_parts if p)

        return CanonicalOrder(
            external_order_id=str(order_data.get("id", "")),
            order_type=FULFILLMENT_MAP.get(fulfillment_type, "delivery"),
            items=items,
            customer_name=customer.get("name", ""),
            customer_phone=customer.get("phone", ""),
            customer_email=customer.get("email", ""),
            delivery_address=address_str,
            subtotal=self._extract_price(price_data, "subtotal"),
            tax_total=self._extract_price(price_data, "tax"),
            delivery_fee=self._extract_price(price_data, "delivery_fee"),
            service_fee=self._extract_price(price_data, "surcharge"),
            tip=self._extract_price(price_data, "tip"),
            discount_total=self._extract_price(price_data, "discount"),
            total=self._extract_price(price_data, "total"),
            placed_at=order_data.get("placed_at"),
            estimated_prep_time=order_data.get("estimated_prep_time"),
            estimated_delivery_time=fulfillment.get("estimated_delivery_time"),
            notes=order_data.get("special_instructions", ""),
            raw_payload=raw_payload,
        )

    def update_order_status(
        self, external_order_id: str, status: str, reason: str = ""
    ) -> bool:
        """
        Push a status change to Deliveroo.

        Deliveroo has two separate mechanisms:
        1. PATCH /order/v1/orders/{id} — accept or reject (only once per order)
        2. POST /order/v1/orders/{id}/prep_stage — preparation stages
        """
        try:
            if status == "accepted":
                return self._patch_order_status(external_order_id, "accepted")
            elif status == "rejected":
                return self._patch_order_status(external_order_id, "rejected", reason)
            elif status in PREP_STAGE_MAP:
                return self._send_prep_stage(
                    external_order_id, PREP_STAGE_MAP[status]
                )
            else:
                # Statuses like 'completed', 'delivered' don't have a Deliveroo API call
                logger.info(
                    "Status '%s' has no Deliveroo API equivalent — skipped.", status
                )
                return True
        except requests.HTTPError as e:
            logger.error(
                "Deliveroo status update failed for order %s: %s",
                external_order_id,
                e.response.text if e.response is not None else str(e),
            )
            return False
        except requests.RequestException as e:
            logger.error("Deliveroo connection error: %s", e)
            return False

    def _patch_order_status(
        self, order_id: str, status: str, reason: str = ""
    ) -> bool:
        payload: dict = {"status": status}
        if status == "rejected" and reason:
            payload["reason"] = reason

        resp = requests.patch(
            f"{self.api_url}/order/v1/orders/{order_id}",
            json=payload,
            headers=self._auth_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return True

    def _send_prep_stage(self, order_id: str, stage: str) -> bool:
        resp = requests.post(
            f"{self.api_url}/order/v1/orders/{order_id}/prep_stage",
            json={
                "stage": stage,
                "occurred_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            headers=self._auth_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return True

    # ── Availability ─────────────────────────────────────────────────

    def update_availability(
        self, items: list[dict], available: bool
    ) -> SyncResult:
        """
        Mark items available/unavailable on Deliveroo.

        Uses POST /v1/brands/{brand_id}/menus/{menu_id}/item-unavailabilities/{site_id}
        """
        if not self.menu_id:
            return SyncResult(
                success=False,
                message="No menu_id configured — push menu first.",
            )

        # Build unavailability payload
        # Deliveroo expects a list of items to mark unavailable.
        # If available=True, we remove them from the unavailability list.
        # If available=False, we add them.
        item_unavailabilities = []
        for item in items:
            plu = item.get("plu", "")
            if not plu:
                continue
            if not available:
                item_unavailabilities.append({
                    "item_id": plu,
                    "status": "unavailable",
                })

        try:
            resp = requests.post(
                f"{self.api_url}/v1/brands/{self.brand_id}/menus/{self.menu_id}"
                f"/item-unavailabilities/{self.site_id}",
                json={"item_unavailabilities": item_unavailabilities},
                headers=self._auth_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return SyncResult(
                success=True,
                message=f"Updated {len(items)} item(s) on Deliveroo.",
                updated_count=len(items),
            )
        except requests.HTTPError as e:
            error_body = e.response.text if e.response is not None else str(e)
            return SyncResult(success=False, message=error_body, errors=[error_body])
        except requests.RequestException as e:
            return SyncResult(success=False, message=str(e), errors=[str(e)])

    # ── Credentials ──────────────────────────────────────────────────

    def validate_credentials(self) -> bool:
        """Test OAuth2 credentials by requesting a token."""
        try:
            self._get_access_token()
            return True
        except (requests.HTTPError, requests.RequestException, KeyError):
            return False

    # ── Webhooks ─────────────────────────────────────────────────────

    def verify_webhook_signature(self, payload: bytes, headers: dict) -> bool:
        """
        Verify Deliveroo's HMAC-SHA256 signature.

        Deliveroo signs: "{sequence_guid} {raw_body}"
        Header: X-Deliveroo-Hmac-Sha256
        """
        if not self.webhook_secret:
            logger.warning("No webhook_secret configured — skipping verification.")
            return True

        signature = headers.get("X-Deliveroo-Hmac-Sha256", "")
        sequence_guid = headers.get("X-Deliveroo-Sequence-Guid", "")

        if not signature:
            return False

        # Deliveroo signs: "{guid} {body}"
        signed_payload = f"{sequence_guid} ".encode() + payload
        expected = hmac.new(
            self.webhook_secret.encode(),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def handle_webhook(
        self, event_type: str, payload: dict, headers: dict
    ) -> WebhookResult:
        """
        Process inbound Deliveroo webhook events.

        Supported events:
        - orders.new → create order
        - orders.status_update → update order status (e.g. customer cancellation)
        - menu.* / item.* → menu change events
        """
        if event_type in ("orders.new", "new_order"):
            return self._handle_new_order(payload)
        elif event_type in ("orders.status_update", "cancel_order"):
            return self._handle_status_update(payload)
        elif event_type.startswith("menu.") or event_type.startswith("item."):
            return self.handle_menu_webhook(event_type, payload, headers)
        else:
            logger.info("Unhandled Deliveroo event: %s", event_type)
            return WebhookResult(
                success=True,
                action="ignored",
                message=f"Event '{event_type}' not handled.",
            )

    def handle_menu_webhook(
        self, event_type: str, payload: dict, headers: dict
    ) -> WebhookResult:
        """
        Handle menu/item change events from Deliveroo.

        For item.86d (unavailable), directly updates local availability.
        For menu.updated, triggers a full pull_and_persist to re-sync.
        """
        if event_type == "item.86d":
            return self._handle_item_unavailable(payload)

        # For menu.updated or other menu events, re-sync from external
        from integrations.services import IntegrationSyncService

        try:
            result = IntegrationSyncService.pull_and_persist(self.channel_link)
            return WebhookResult(
                success=result.success,
                action="menu_synced",
                message=result.message,
            )
        except Exception as e:
            logger.exception("Failed to sync menu from Deliveroo webhook")
            return WebhookResult(
                success=False,
                action="menu_sync_failed",
                message=str(e),
            )

    def _handle_item_unavailable(self, payload: dict) -> WebhookResult:
        """Mark items as unavailable based on Deliveroo 86'd event."""
        from products.models import Product, ProductLocation

        items = payload.get("items", [])
        if not items:
            item_id = payload.get("item_id") or payload.get("plu")
            if item_id:
                items = [{"plu": item_id}]

        updated = 0
        for item in items:
            plu = item.get("plu", item.get("item_id", ""))
            if not plu:
                continue
            count = ProductLocation.objects.filter(
                product__plu=plu,
                location=self.location,
            ).update(is_available=False)
            updated += count

        return WebhookResult(
            success=True,
            action="items_86d",
            message=f"Marked {updated} product-locations as unavailable.",
        )

    def _handle_new_order(self, payload: dict) -> WebhookResult:
        """Create an order from a Deliveroo new-order webhook."""
        from orders.services import OrderService

        try:
            canonical = self.normalize_inbound_order(payload)
            order = OrderService.create_order_from_canonical(
                canonical_order=canonical,
                location=self.location,
                channel=self.channel_link.channel,
                channel_link=self.channel_link,
            )
            return WebhookResult(
                success=True,
                action="order_created",
                message=f"Order {order.order_number} created.",
                order_id=str(order.id),
            )
        except Exception as e:
            logger.exception("Failed to create order from Deliveroo webhook")
            return WebhookResult(
                success=False,
                action="order_create_failed",
                message=str(e),
            )

    def _handle_status_update(self, payload: dict) -> WebhookResult:
        """Handle order status updates (e.g. cancellations from Deliveroo)."""
        from orders.models import Order, OrderStatus
        from orders.services import OrderService

        order_data = payload.get("order", payload)
        external_id = str(order_data.get("id", ""))
        new_status_raw = order_data.get("status", "")

        status_map = {
            "cancelled": OrderStatus.CANCELLED,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        new_status = status_map.get(new_status_raw)
        if not new_status:
            return WebhookResult(
                success=True,
                action="ignored",
                message=f"Status '{new_status_raw}' not mapped.",
            )

        try:
            order = Order.objects.get(external_order_id=external_id)
            OrderService.transition_status(
                order,
                new_status,
                changed_by="deliveroo",
                reason=order_data.get("cancel_reason", "Deliveroo status update"),
            )
            return WebhookResult(
                success=True,
                action="status_updated",
                message=f"Order {order.order_number} → {new_status}",
                order_id=str(order.id),
            )
        except Order.DoesNotExist:
            return WebhookResult(
                success=False,
                action="order_not_found",
                message=f"No order with external_id '{external_id}'.",
            )
        except Exception as e:
            logger.exception("Failed to update order status from Deliveroo webhook")
            return WebhookResult(success=False, action="status_update_failed", message=str(e))

    # ── Lifecycle hooks ──────────────────────────────────────────────

    def on_link_activated(self) -> None:
        logger.info(
            "Deliveroo link activated: brand=%s site=%s",
            self.brand_id,
            self.site_id,
        )

    def on_link_deactivated(self) -> None:
        logger.info(
            "Deliveroo link deactivated: brand=%s site=%s",
            self.brand_id,
            self.site_id,
        )

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_price(data: dict, key: str) -> int:
        """
        Extract price in minor units from Deliveroo's price objects.

        Deliveroo uses either:
        - {"fractional": 350, "currency_code": "GBP"}
        - plain integer
        """
        val = data.get(key, 0)
        if isinstance(val, dict):
            return val.get("fractional", 0)
        if isinstance(val, (int, float)):
            return int(val)
        return 0

    @staticmethod
    def _slugify(text: str) -> str:
        """Simple slug: lowercase, replace spaces/special chars with hyphens."""
        import re
        slug = text.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")
