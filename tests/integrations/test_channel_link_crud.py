from tests.base import BaseAPITest


class TestChannelLinkCRUD(BaseAPITest):

    def test_create_channel_link(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        channel = self.create_channel()

        res = self.client.post(
            "/api/v1/channel-links/",
            {"channel": str(channel.id), "location": str(location_id)},
            format="json",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["channel_slug"], "internal_pos")

    def test_list_channel_links(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        channel = self.create_channel()
        self.create_channel_link(channel, location_id, merchant_id)

        res = self.client.get(
            "/api/v1/channel-links/",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)

    def test_channel_link_requires_tenant_header(self):
        user, pwd = self.create_user()
        self.authenticate(user.email, pwd)

        res = self.client.get("/api/v1/channel-links/")
        self.assertEqual(res.status_code, 400)

    def test_unique_constraint_channel_location(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        channel = self.create_channel()

        # First link
        self.create_channel_link(channel, location_id, merchant_id)

        # Duplicate should fail
        res = self.client.post(
            "/api/v1/channel-links/",
            {"channel": str(channel.id), "location": str(location_id)},
            format="json",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 400)

    def test_validate_action(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        channel = self.create_channel()
        link_id = self.create_channel_link(channel, location_id, merchant_id)

        res = self.client.post(
            f"/api/v1/channel-links/{link_id}/validate/",
            **self.merchant_headers(merchant_id),
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["valid"])

    def test_tenant_isolation(self):
        # User A
        user_a, pass_a, merchant_a = self.setup_user_and_merchant(email="a@test.com", name="Merchant A")
        loc_a = self.create_location(merchant_a)
        channel = self.create_channel()
        self.create_channel_link(channel, loc_a, merchant_a)

        # User B
        self.client.credentials()
        user_b, pass_b, merchant_b = self.setup_user_and_merchant(email="b@test.com", name="Merchant B")

        # B should not see A's links
        res = self.client.get(
            "/api/v1/channel-links/",
            **self.merchant_headers(merchant_b),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 0)
