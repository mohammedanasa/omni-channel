from tests.base import BaseAPITest


class TestOrderCRUD(BaseAPITest):

    def test_create_order(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)

        order = self.create_order(merchant_id, location_id)
        self.assertIn("order_number", order)
        self.assertTrue(order["order_number"].startswith("ORD-"))

    def test_list_orders(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        self.create_order(merchant_id, location_id)
        self.create_order(merchant_id, location_id, customer_name="Customer B")

        res = self.client.get(
            "/api/v1/orders/",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 2)

    def test_retrieve_order_detail(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        order = self.create_order(merchant_id, location_id)

        res = self.client.get(
            f"/api/v1/orders/{order['id']}/",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("items", res.json())
        self.assertIn("status_logs", res.json())

    def test_order_requires_tenant(self):
        user, pwd = self.create_user()
        self.authenticate(user.email, pwd)

        res = self.client.get("/api/v1/orders/")
        self.assertEqual(res.status_code, 400)

    def test_tenant_isolation(self):
        # User A
        user_a, pass_a, merchant_a = self.setup_user_and_merchant(email="a@test.com", name="Merchant A")
        loc_a = self.create_location(merchant_a)
        self.create_order(merchant_a, loc_a, customer_name="A-Customer")

        # User B
        self.client.credentials()
        user_b, pass_b, merchant_b = self.setup_user_and_merchant(email="b@test.com", name="Merchant B")
        loc_b = self.create_location(merchant_b)

        # B should see no orders
        res = self.client.get(
            "/api/v1/orders/",
            **self.merchant_headers(merchant_b),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 0)
