from django.db import connection
from accounts.models import Merchant
from tests.base import BaseAPITest


class TestProductChannelConfig(BaseAPITest):

    def test_create_product_channel_config(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        channel = self.create_channel()

        headers = self.merchant_headers(merchant_id)
        self.client.post(
            "/api/v1/categories/",
            {"name": "Burgers", "pos_category_id": "CAT-001"},
            format="json",
            **headers,
        )
        prod_res = self.client.post(
            "/api/v1/products/",
            {
                "name": "Burger",
                "product_type": 1,
                "price": 999,
                "locations": [{"location_id": str(location_id), "price_override": 999}],
            },
            format="json",
            **headers,
        )
        self.assertEqual(prod_res.status_code, 201, prod_res.json())

        # Get ProductLocation ID — must be in tenant schema
        tenant = Merchant.objects.get(id=merchant_id)
        connection.set_tenant(tenant)
        from products.models import ProductLocation
        pl = ProductLocation.objects.first()
        connection.set_schema_to_public()
        self.assertIsNotNone(pl)

        # Create config
        res = self.client.post(
            "/api/v1/product-channel-configs/",
            {
                "product_location": str(pl.id),
                "channel": str(channel.id),
                "price": 1099,
                "is_available": True,
            },
            format="json",
            **headers,
        )
        self.assertEqual(res.status_code, 201, res.json())
        self.assertEqual(res.json()["price"], 1099)
        self.assertEqual(res.json()["channel_slug"], "internal_pos")
