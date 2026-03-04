from django.db import connection
from accounts.models import Merchant
from tests.base import BaseAPITest
from integrations.canonical.orders import CanonicalOrder, CanonicalOrderItem, CanonicalOrderModifier
from orders.services import OrderService
from orders.models import Order


class TestOrderService(BaseAPITest):

    def test_create_order_from_canonical(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)

        # Switch to tenant schema for direct model access
        tenant = Merchant.objects.get(id=merchant_id)
        connection.set_tenant(tenant)

        from locations.models import Location
        location = Location.objects.get(id=location_id)

        canonical = CanonicalOrder(
            external_order_id="EXT-001",
            order_type="delivery",
            items=[
                CanonicalOrderItem(
                    plu="P001",
                    name="Burger",
                    quantity=2,
                    unit_price=999,
                    modifiers=[
                        CanonicalOrderModifier(
                            plu="M001",
                            name="Extra Cheese",
                            quantity=1,
                            unit_price=50,
                            group_name="Toppings",
                        ),
                    ],
                ),
            ],
            customer_name="John Doe",
            subtotal=2048,
            tax_total=200,
            total=2248,
        )

        order = OrderService.create_order_from_canonical(canonical, location)
        self.assertIsInstance(order, Order)
        self.assertTrue(order.order_number.startswith("ORD-"))
        self.assertEqual(order.external_order_id, "EXT-001")
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().modifiers.count(), 1)
        self.assertEqual(order.status_logs.count(), 1)

        connection.set_schema_to_public()
