from tests.base import BaseAPITest


class TestOrderStateMachine(BaseAPITest):

    def _create_and_get_order(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        order = self.create_order(merchant_id, location_id)
        return order, merchant_id

    def test_valid_transition_received_to_accepted(self):
        order, merchant_id = self._create_and_get_order()

        res = self.client.patch(
            f"/api/v1/orders/{order['id']}/status/",
            {"status": "accepted"},
            format="json",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "accepted")

    def test_full_happy_path(self):
        order, merchant_id = self._create_and_get_order()
        headers = self.merchant_headers(merchant_id)
        order_url = f"/api/v1/orders/{order['id']}/status/"

        for target in ["accepted", "preparing", "ready", "completed"]:
            res = self.client.patch(order_url, {"status": target}, format="json", **headers)
            self.assertEqual(res.status_code, 200, f"Failed at transition to {target}: {res.json()}")
            self.assertEqual(res.json()["status"], target)

    def test_invalid_transition_received_to_delivered(self):
        order, merchant_id = self._create_and_get_order()

        res = self.client.patch(
            f"/api/v1/orders/{order['id']}/status/",
            {"status": "delivered"},
            format="json",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 400)

    def test_invalid_transition_completed_to_anything(self):
        order, merchant_id = self._create_and_get_order()
        headers = self.merchant_headers(merchant_id)
        order_url = f"/api/v1/orders/{order['id']}/status/"

        # Move to completed
        for target in ["accepted", "preparing", "ready", "completed"]:
            self.client.patch(order_url, {"status": target}, format="json", **headers)

        # Try to move from completed — should fail
        res = self.client.patch(order_url, {"status": "accepted"}, format="json", **headers)
        self.assertEqual(res.status_code, 400)

    def test_rejection_from_received(self):
        order, merchant_id = self._create_and_get_order()

        res = self.client.patch(
            f"/api/v1/orders/{order['id']}/status/",
            {"status": "rejected", "reason": "Out of stock"},
            format="json",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "rejected")

    def test_status_logs_recorded(self):
        order, merchant_id = self._create_and_get_order()
        headers = self.merchant_headers(merchant_id)
        order_url = f"/api/v1/orders/{order['id']}/status/"

        self.client.patch(order_url, {"status": "accepted"}, format="json", **headers)
        self.client.patch(order_url, {"status": "preparing"}, format="json", **headers)

        detail = self.client.get(
            f"/api/v1/orders/{order['id']}/",
            **headers,
        )
        logs = detail.json()["status_logs"]
        # Initial log + 2 transitions = 3
        self.assertEqual(len(logs), 3)

    def test_timestamp_set_on_accepted(self):
        order, merchant_id = self._create_and_get_order()

        res = self.client.patch(
            f"/api/v1/orders/{order['id']}/status/",
            {"status": "accepted"},
            format="json",
            **self.merchant_headers(merchant_id),
        )
        self.assertIsNotNone(res.json()["accepted_at"])
