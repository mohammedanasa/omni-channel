"""
Tests for the Deliveroo adapter.

These tests use mocked HTTP responses — no real Deliveroo API calls are made.
"""

import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

from django.test import TestCase

from integrations.adapters.deliveroo import DeliverooAdapter, PREP_STAGE_MAP
from integrations.canonical.menu import (
    CanonicalMenu,
    CanonicalModifier,
    CanonicalModifierGroup,
    CanonicalProduct,
)
from integrations.canonical.orders import CanonicalOrder


# ── Fixtures ─────────────────────────────────────────────────────────

SAMPLE_CREDENTIALS = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "brand_id": "brand-123",
    "site_id": "site-456",
    "menu_id": "menu-789",
    "webhook_secret": "whsec_test_secret",
    "environment": "sandbox",
}

SAMPLE_DELIVEROO_ORDER_PAYLOAD = {
    "event": "orders.new",
    "order": {
        "id": "DRO-123456",
        "status": "placed",
        "placed_at": "2026-03-08T12:00:00Z",
        "special_instructions": "No onions please",
        "items": [
            {
                "id": "item-1",
                "plu": "BURG-001",
                "name": "Classic Burger",
                "quantity": 2,
                "total_price": {"fractional": 1800, "currency_code": "GBP"},
                "modifiers": [
                    {
                        "id": "mod-group-1",
                        "name": "Extras",
                        "options": [
                            {
                                "id": "opt-1",
                                "plu": "MOD-CHEESE",
                                "name": "Extra Cheese",
                                "quantity": 1,
                                "total_price": {"fractional": 150, "currency_code": "GBP"},
                            }
                        ],
                    }
                ],
            },
            {
                "id": "item-2",
                "plu": "FRIES-001",
                "name": "Large Fries",
                "quantity": 1,
                "total_price": {"fractional": 450, "currency_code": "GBP"},
                "modifiers": [],
            },
        ],
        "price": {
            "subtotal": {"fractional": 2250, "currency_code": "GBP"},
            "tax": {"fractional": 375, "currency_code": "GBP"},
            "delivery_fee": {"fractional": 299, "currency_code": "GBP"},
            "surcharge": {"fractional": 50, "currency_code": "GBP"},
            "tip": {"fractional": 200, "currency_code": "GBP"},
            "discount": {"fractional": 0, "currency_code": "GBP"},
            "total": {"fractional": 3174, "currency_code": "GBP"},
        },
        "customer": {
            "name": "John Doe",
            "phone": "+447700900000",
            "email": "john@example.com",
        },
        "fulfillment": {
            "type": "DELIVERY",
            "delivery_address": {
                "address_line1": "123 High Street",
                "address_line2": "Flat 4",
                "city": "London",
                "post_code": "SW1A 1AA",
            },
            "estimated_delivery_time": "2026-03-08T12:45:00Z",
        },
    },
}


def _make_mock_channel_link(credentials=None):
    """Create a mock ChannelLink for testing."""
    link = MagicMock()
    link.credentials = credentials or SAMPLE_CREDENTIALS.copy()
    link.location = MagicMock()
    link.location.id = "loc-uuid-123"
    link.location.name = "Test Location"
    link.channel = MagicMock()
    link.channel.slug = "deliveroo"
    link.save = MagicMock()
    return link


def _make_adapter(credentials=None):
    link = _make_mock_channel_link(credentials)
    # Clear token cache for clean test state
    DeliverooAdapter._token_cache.clear()
    return DeliverooAdapter(link)


# ── Test Classes ─────────────────────────────────────────────────────


class TestDeliverooOrderNormalization(TestCase):
    """Test converting Deliveroo payloads → CanonicalOrder."""

    def setUp(self):
        self.adapter = _make_adapter()

    def test_normalize_order_basic_fields(self):
        order = self.adapter.normalize_inbound_order(SAMPLE_DELIVEROO_ORDER_PAYLOAD)

        self.assertIsInstance(order, CanonicalOrder)
        self.assertEqual(order.external_order_id, "DRO-123456")
        self.assertEqual(order.order_type, "delivery")
        self.assertEqual(order.customer_name, "John Doe")
        self.assertEqual(order.customer_phone, "+447700900000")
        self.assertEqual(order.customer_email, "john@example.com")
        self.assertEqual(order.notes, "No onions please")
        self.assertEqual(order.placed_at, "2026-03-08T12:00:00Z")

    def test_normalize_order_items(self):
        order = self.adapter.normalize_inbound_order(SAMPLE_DELIVEROO_ORDER_PAYLOAD)

        self.assertEqual(len(order.items), 2)

        burger = order.items[0]
        self.assertEqual(burger.plu, "BURG-001")
        self.assertEqual(burger.name, "Classic Burger")
        self.assertEqual(burger.quantity, 2)
        self.assertEqual(burger.unit_price, 1800)
        self.assertEqual(burger.external_item_id, "item-1")

        fries = order.items[1]
        self.assertEqual(fries.plu, "FRIES-001")
        self.assertEqual(fries.quantity, 1)
        self.assertEqual(fries.unit_price, 450)

    def test_normalize_order_modifiers(self):
        order = self.adapter.normalize_inbound_order(SAMPLE_DELIVEROO_ORDER_PAYLOAD)

        burger = order.items[0]
        self.assertEqual(len(burger.modifiers), 1)

        mod = burger.modifiers[0]
        self.assertEqual(mod.plu, "MOD-CHEESE")
        self.assertEqual(mod.name, "Extra Cheese")
        self.assertEqual(mod.unit_price, 150)
        self.assertEqual(mod.group_name, "Extras")

    def test_normalize_order_financials(self):
        order = self.adapter.normalize_inbound_order(SAMPLE_DELIVEROO_ORDER_PAYLOAD)

        self.assertEqual(order.subtotal, 2250)
        self.assertEqual(order.tax_total, 375)
        self.assertEqual(order.delivery_fee, 299)
        self.assertEqual(order.service_fee, 50)
        self.assertEqual(order.tip, 200)
        self.assertEqual(order.discount_total, 0)
        self.assertEqual(order.total, 3174)

    def test_normalize_order_delivery_address(self):
        order = self.adapter.normalize_inbound_order(SAMPLE_DELIVEROO_ORDER_PAYLOAD)
        self.assertIn("123 High Street", order.delivery_address)
        self.assertIn("Flat 4", order.delivery_address)
        self.assertIn("London", order.delivery_address)
        self.assertIn("SW1A 1AA", order.delivery_address)

    def test_normalize_order_pickup_type(self):
        payload = json.loads(json.dumps(SAMPLE_DELIVEROO_ORDER_PAYLOAD))
        payload["order"]["fulfillment"]["type"] = "PICKUP"
        order = self.adapter.normalize_inbound_order(payload)
        self.assertEqual(order.order_type, "pickup")

    def test_normalize_order_raw_payload_preserved(self):
        order = self.adapter.normalize_inbound_order(SAMPLE_DELIVEROO_ORDER_PAYLOAD)
        self.assertEqual(order.raw_payload, SAMPLE_DELIVEROO_ORDER_PAYLOAD)

    def test_normalize_order_to_order_kwargs(self):
        """Verify the canonical order can produce kwargs for Order.objects.create()."""
        order = self.adapter.normalize_inbound_order(SAMPLE_DELIVEROO_ORDER_PAYLOAD)
        kwargs = order.to_order_kwargs()

        self.assertEqual(kwargs["external_order_id"], "DRO-123456")
        self.assertEqual(kwargs["order_type"], "delivery")
        self.assertEqual(kwargs["total"], 3174)
        self.assertIn("raw_payload", kwargs)


class TestDeliverooMenuConversion(TestCase):
    """Test converting CanonicalMenu → Deliveroo menu JSON."""

    def setUp(self):
        self.adapter = _make_adapter()

    def _make_sample_menu(self):
        return CanonicalMenu(
            location_id="loc-123",
            location_name="Test Store",
            channel_slug="deliveroo",
            categories=["Burgers", "Sides"],
            products=[
                CanonicalProduct(
                    plu="BURG-001",
                    name="Classic Burger",
                    description="A tasty burger",
                    price=900,
                    image_url="https://example.com/burger.jpg",
                    is_available=True,
                    category_name="Burgers",
                    modifier_groups=[
                        CanonicalModifierGroup(
                            plu="MG-EXTRAS",
                            name="Extras",
                            min_select=0,
                            max_select=3,
                            modifiers=[
                                CanonicalModifier(plu="MOD-CHEESE", name="Extra Cheese", price=150),
                                CanonicalModifier(plu="MOD-BACON", name="Bacon", price=200),
                            ],
                        ),
                    ],
                ),
                CanonicalProduct(
                    plu="FRIES-001",
                    name="Large Fries",
                    price=450,
                    category_name="Sides",
                ),
            ],
        )

    def test_menu_structure(self):
        menu = self._make_sample_menu()
        result = self.adapter._canonical_to_deliveroo_menu(menu)

        self.assertIn("menu", result)
        self.assertIn("categories", result["menu"])
        self.assertIn("items", result["menu"])
        self.assertIn("modifiers", result["menu"])
        self.assertEqual(result["site_ids"], ["site-456"])

    def test_menu_categories(self):
        menu = self._make_sample_menu()
        result = self.adapter._canonical_to_deliveroo_menu(menu)
        cats = result["menu"]["categories"]

        cat_names = [c["name"]["en"] for c in cats]
        self.assertIn("Burgers", cat_names)
        self.assertIn("Sides", cat_names)

    def test_menu_items(self):
        menu = self._make_sample_menu()
        result = self.adapter._canonical_to_deliveroo_menu(menu)
        items = result["menu"]["items"]

        # Should have 2 main items + 2 modifier choices = 4
        item_types = [i.get("type") for i in items]
        self.assertEqual(item_types.count("ITEM"), 2)
        self.assertEqual(item_types.count("CHOICE"), 2)

    def test_menu_items_have_plu(self):
        menu = self._make_sample_menu()
        result = self.adapter._canonical_to_deliveroo_menu(menu)
        items = result["menu"]["items"]

        for item in items:
            self.assertIn("plu", item)
            self.assertTrue(item["plu"])

    def test_menu_modifiers(self):
        menu = self._make_sample_menu()
        result = self.adapter._canonical_to_deliveroo_menu(menu)
        mods = result["menu"]["modifiers"]

        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]["name"]["en"], "Extras")
        self.assertEqual(mods[0]["min_selection"], 0)
        self.assertEqual(mods[0]["max_selection"], 3)
        self.assertEqual(len(mods[0]["item_ids"]), 2)

    def test_menu_price_in_minor_units(self):
        menu = self._make_sample_menu()
        result = self.adapter._canonical_to_deliveroo_menu(menu)
        items = result["menu"]["items"]

        burger = next(i for i in items if i["plu"] == "BURG-001")
        self.assertEqual(burger["price_info"]["price"], 900)

    def test_menu_image_url(self):
        menu = self._make_sample_menu()
        result = self.adapter._canonical_to_deliveroo_menu(menu)
        items = result["menu"]["items"]

        burger = next(i for i in items if i["plu"] == "BURG-001")
        self.assertEqual(burger["image_url"], "https://example.com/burger.jpg")


class TestDeliverooWebhookVerification(TestCase):
    """Test HMAC-SHA256 webhook signature verification."""

    def setUp(self):
        self.adapter = _make_adapter()

    def test_valid_signature(self):
        body = b'{"event":"orders.new","order":{"id":"123"}}'
        guid = "test-guid-12345"

        signed_payload = f"{guid} ".encode() + body
        signature = hmac.new(
            b"whsec_test_secret", signed_payload, hashlib.sha256
        ).hexdigest()

        headers = {
            "X-Deliveroo-Hmac-Sha256": signature,
            "X-Deliveroo-Sequence-Guid": guid,
        }

        self.assertTrue(self.adapter.verify_webhook_signature(body, headers))

    def test_invalid_signature(self):
        body = b'{"event":"orders.new"}'
        headers = {
            "X-Deliveroo-Hmac-Sha256": "invalid_signature",
            "X-Deliveroo-Sequence-Guid": "guid",
        }
        self.assertFalse(self.adapter.verify_webhook_signature(body, headers))

    def test_missing_signature_header(self):
        body = b'{"event":"orders.new"}'
        headers = {"X-Deliveroo-Sequence-Guid": "guid"}
        self.assertFalse(self.adapter.verify_webhook_signature(body, headers))

    def test_no_webhook_secret_skips_verification(self):
        adapter = _make_adapter(
            {**SAMPLE_CREDENTIALS, "webhook_secret": ""}
        )
        body = b'{"event":"orders.new"}'
        headers = {}
        self.assertTrue(adapter.verify_webhook_signature(body, headers))


class TestDeliverooTokenManagement(TestCase):
    """Test OAuth2 token caching and refresh."""

    def setUp(self):
        DeliverooAdapter._token_cache.clear()

    @patch("integrations.adapters.deliveroo.requests.post")
    def test_get_access_token(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "test-jwt-token",
            "token_type": "Bearer",
            "expires_in": 300,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        adapter = _make_adapter()
        token = adapter._get_access_token()

        self.assertEqual(token, "test-jwt-token")
        mock_post.assert_called_once()

    @patch("integrations.adapters.deliveroo.requests.post")
    def test_token_caching(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "cached-token",
            "expires_in": 300,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        adapter = _make_adapter()
        token1 = adapter._get_access_token()
        token2 = adapter._get_access_token()

        self.assertEqual(token1, token2)
        # Should only call the auth endpoint once (cached)
        self.assertEqual(mock_post.call_count, 1)

    @patch("integrations.adapters.deliveroo.requests.post")
    def test_validate_credentials_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "t", "expires_in": 300}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        adapter = _make_adapter()
        self.assertTrue(adapter.validate_credentials())

    @patch("integrations.adapters.deliveroo.requests.post")
    def test_validate_credentials_failure(self, mock_post):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.side_effect = req.HTTPError(response=mock_resp)

        adapter = _make_adapter()
        self.assertFalse(adapter.validate_credentials())


class TestDeliverooStatusUpdate(TestCase):
    """Test order status updates to Deliveroo API."""

    def setUp(self):
        self.adapter = _make_adapter()

    @patch("integrations.adapters.deliveroo.requests.post")
    @patch("integrations.adapters.deliveroo.requests.patch")
    def test_accept_order(self, mock_patch, mock_post):
        # Mock token request
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "t", "expires_in": 300}
        mock_token_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_token_resp

        # Mock PATCH
        mock_patch_resp = MagicMock()
        mock_patch_resp.raise_for_status = MagicMock()
        mock_patch.return_value = mock_patch_resp

        result = self.adapter.update_order_status("DRO-123", "accepted")
        self.assertTrue(result)
        mock_patch.assert_called_once()

    @patch("integrations.adapters.deliveroo.requests.post")
    def test_preparing_sends_prep_stage(self, mock_post):
        # First call = token, second call = prep stage
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "t", "expires_in": 300}
        mock_token_resp.raise_for_status = MagicMock()

        mock_prep_resp = MagicMock()
        mock_prep_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [mock_token_resp, mock_prep_resp]

        result = self.adapter.update_order_status("DRO-123", "preparing")
        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)

    def test_completed_status_is_noop(self):
        """Statuses with no Deliveroo equivalent should succeed silently."""
        result = self.adapter.update_order_status("DRO-123", "completed")
        self.assertTrue(result)


class TestDeliverooMenuPush(TestCase):
    """Test pushing menu to Deliveroo API."""

    @patch("integrations.adapters.deliveroo.requests.post")
    @patch("integrations.adapters.deliveroo.requests.put")
    def test_push_menu_success(self, mock_put, mock_post):
        # Token
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "t", "expires_in": 300}
        mock_token_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_token_resp

        # Menu push
        mock_put_resp = MagicMock()
        mock_put_resp.raise_for_status = MagicMock()
        mock_put_resp.content = b'{}'
        mock_put_resp.json.return_value = {}
        mock_put.return_value = mock_put_resp

        adapter = _make_adapter()
        menu = CanonicalMenu(
            location_id="loc-1",
            location_name="Store",
            channel_slug="deliveroo",
            categories=["Mains"],
            products=[
                CanonicalProduct(plu="P1", name="Burger", price=900, category_name="Mains"),
            ],
        )

        result = adapter.push_menu(menu)
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 1)
        mock_put.assert_called_once()

    @patch("integrations.adapters.deliveroo.requests.post")
    @patch("integrations.adapters.deliveroo.requests.put")
    def test_push_menu_api_error(self, mock_put, mock_post):
        import requests as req

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "t", "expires_in": 300}
        mock_token_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_token_resp

        mock_err_resp = MagicMock()
        mock_err_resp.status_code = 400
        mock_err_resp.text = "Invalid menu format"
        mock_put.side_effect = req.HTTPError(response=mock_err_resp)

        adapter = _make_adapter()
        menu = CanonicalMenu(
            location_id="loc-1", location_name="Store",
            channel_slug="deliveroo", products=[],
        )

        result = adapter.push_menu(menu)
        self.assertFalse(result.success)
        self.assertIn("400", result.message)


class TestDeliverooAvailability(TestCase):
    """Test item availability updates."""

    @patch("integrations.adapters.deliveroo.requests.post")
    def test_mark_unavailable(self, mock_post):
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "t", "expires_in": 300}
        mock_token_resp.raise_for_status = MagicMock()

        mock_avail_resp = MagicMock()
        mock_avail_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [mock_token_resp, mock_avail_resp]

        adapter = _make_adapter()
        result = adapter.update_availability(
            [{"plu": "BURG-001"}, {"plu": "FRIES-001"}],
            available=False,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 2)

    def test_no_menu_id_returns_error(self):
        adapter = _make_adapter({**SAMPLE_CREDENTIALS, "menu_id": ""})
        result = adapter.update_availability([{"plu": "P1"}], available=False)
        self.assertFalse(result.success)
        self.assertIn("menu_id", result.message)


class TestDeliverooHelpers(TestCase):
    """Test helper methods."""

    def test_extract_price_from_dict(self):
        data = {"subtotal": {"fractional": 1500, "currency_code": "GBP"}}
        self.assertEqual(DeliverooAdapter._extract_price(data, "subtotal"), 1500)

    def test_extract_price_from_int(self):
        data = {"subtotal": 1500}
        self.assertEqual(DeliverooAdapter._extract_price(data, "subtotal"), 1500)

    def test_extract_price_missing_key(self):
        self.assertEqual(DeliverooAdapter._extract_price({}, "subtotal"), 0)

    def test_slugify(self):
        self.assertEqual(DeliverooAdapter._slugify("Burgers & More"), "burgers-more")
        self.assertEqual(DeliverooAdapter._slugify("  Sides  "), "sides")
