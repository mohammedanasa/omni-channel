from unittest.mock import MagicMock

from django.test import TestCase

from integrations.adapters.internal import InternalPOSAdapter
from integrations.canonical.orders import CanonicalOrder
from integrations.canonical.results import SyncResult, WebhookResult


class TestInternalAdapter(TestCase):

    def setUp(self):
        self.link = MagicMock()
        self.link.credentials = {}
        self.link.location = MagicMock()
        self.link.location.id = "loc-uuid"
        self.link.location.name = "Main Store"
        self.adapter = InternalPOSAdapter(self.link)

    def test_push_menu_noop(self):
        result = self.adapter.push_menu(MagicMock())
        self.assertIsInstance(result, SyncResult)
        self.assertTrue(result.success)

    def test_validate_credentials_always_true(self):
        self.assertTrue(self.adapter.validate_credentials())

    def test_verify_webhook_signature_always_true(self):
        self.assertTrue(self.adapter.verify_webhook_signature(b"", {}))

    def test_handle_webhook_noop(self):
        result = self.adapter.handle_webhook("test", {}, {})
        self.assertIsInstance(result, WebhookResult)
        self.assertTrue(result.success)
        self.assertEqual(result.action, "noop")

    def test_update_order_status_always_true(self):
        self.assertTrue(self.adapter.update_order_status("ext-123", "accepted"))

    def test_normalize_inbound_order(self):
        payload = {
            "external_order_id": "ORD-001",
            "order_type": "delivery",
            "items": [
                {"plu": "P001", "name": "Burger", "quantity": 2, "unit_price": 999}
            ],
            "total": 1998,
        }
        order = self.adapter.normalize_inbound_order(payload)
        self.assertIsInstance(order, CanonicalOrder)
        self.assertEqual(order.external_order_id, "ORD-001")
        self.assertEqual(len(order.items), 1)
        self.assertEqual(order.items[0].plu, "P001")
