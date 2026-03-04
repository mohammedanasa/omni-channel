from django.test import TestCase

from integrations.canonical.menu import (
    CanonicalModifier,
    CanonicalModifierGroup,
    CanonicalProduct,
    CanonicalMenu,
)
from integrations.canonical.orders import (
    CanonicalOrderModifier,
    CanonicalOrderItem,
    CanonicalOrder,
)
from integrations.canonical.results import SyncResult, WebhookResult


class TestCanonicalMenu(TestCase):

    def test_canonical_product_to_dict(self):
        p = CanonicalProduct(plu="P1", name="Burger", price=999)
        d = p.to_dict()
        self.assertEqual(d["plu"], "P1")
        self.assertEqual(d["price"], 999)

    def test_canonical_menu_to_dict(self):
        menu = CanonicalMenu(
            location_id="loc-1",
            location_name="Store A",
            channel_slug="internal_pos",
            products=[CanonicalProduct(plu="P1", name="Burger", price=999)],
            categories=["Burgers"],
        )
        d = menu.to_dict()
        self.assertEqual(d["location_id"], "loc-1")
        self.assertEqual(len(d["products"]), 1)

    def test_modifier_group_nesting(self):
        mg = CanonicalModifierGroup(
            plu="MG1",
            name="Toppings",
            modifiers=[
                CanonicalModifier(plu="M1", name="Cheese", price=50),
                CanonicalModifier(plu="M2", name="Lettuce", price=0),
            ],
        )
        d = mg.to_dict()
        self.assertEqual(len(d["modifiers"]), 2)


class TestCanonicalOrder(TestCase):

    def test_order_item_total_price(self):
        item = CanonicalOrderItem(
            plu="P1", name="Burger", quantity=2, unit_price=999,
            modifiers=[
                CanonicalOrderModifier(plu="M1", name="Cheese", quantity=2, unit_price=50),
            ],
        )
        # 2 * 999 + 2 * 50 = 2098
        self.assertEqual(item.total_price, 2098)

    def test_from_dict_round_trip(self):
        data = {
            "external_order_id": "EXT-001",
            "order_type": "delivery",
            "items": [
                {
                    "plu": "P1",
                    "name": "Burger",
                    "quantity": 1,
                    "unit_price": 999,
                    "modifiers": [
                        {"plu": "M1", "name": "Cheese", "quantity": 1, "unit_price": 50},
                    ],
                },
            ],
            "customer_name": "John Doe",
            "subtotal": 1049,
            "tax_total": 100,
            "total": 1149,
        }
        order = CanonicalOrder.from_dict(data)
        self.assertEqual(order.external_order_id, "EXT-001")
        self.assertEqual(len(order.items), 1)
        self.assertEqual(order.items[0].modifiers[0].name, "Cheese")

        kwargs = order.to_order_kwargs()
        self.assertEqual(kwargs["external_order_id"], "EXT-001")
        self.assertEqual(kwargs["subtotal"], 1049)
        self.assertEqual(kwargs["total"], 1149)

    def test_to_dict_includes_total_price(self):
        item = CanonicalOrderItem(plu="P1", name="Burger", quantity=2, unit_price=500)
        d = item.to_dict()
        self.assertEqual(d["total_price"], 1000)


class TestSyncResult(TestCase):

    def test_sync_result_to_dict(self):
        r = SyncResult(success=True, message="OK", updated_count=5)
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["updated_count"], 5)


class TestWebhookResult(TestCase):

    def test_webhook_result_to_dict(self):
        r = WebhookResult(success=True, action="order_created", order_id="123")
        d = r.to_dict()
        self.assertEqual(d["action"], "order_created")
        self.assertEqual(d["order_id"], "123")
