from tests.base import BaseAPITest
from channels.models import Channel


class TestChannelCRUD(BaseAPITest):

    def setUp(self):
        self.channel = Channel.objects.create(
            slug="internal_pos",
            display_name="Internal POS",
            channel_type="pos",
            direction="bidirectional",
            adapter_class="integrations.adapters.internal.InternalPOSAdapter",
        )
        Channel.objects.create(
            slug="ubereats",
            display_name="Uber Eats",
            channel_type="marketplace",
            direction="inbound",
            adapter_class="integrations.adapters.internal.InternalPOSAdapter",
        )

    def test_list_channels_authenticated(self):
        user, pwd = self.create_user()
        self.authenticate(user.email, pwd)

        res = self.client.get("/api/v1/channels/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 2)

    def test_list_channels_unauthenticated(self):
        res = self.client.get("/api/v1/channels/")
        self.assertEqual(res.status_code, 401)

    def test_retrieve_channel(self):
        user, pwd = self.create_user()
        self.authenticate(user.email, pwd)

        res = self.client.get(f"/api/v1/channels/{self.channel.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["slug"], "internal_pos")

    def test_channels_are_read_only(self):
        user, pwd = self.create_user()
        self.authenticate(user.email, pwd)

        # POST should not be allowed (read-only viewset)
        res = self.client.post("/api/v1/channels/", {
            "slug": "new_channel",
            "display_name": "New Channel",
        })
        self.assertEqual(res.status_code, 405)

    def test_inactive_channels_hidden(self):
        user, pwd = self.create_user()
        self.authenticate(user.email, pwd)

        self.channel.is_active = False
        self.channel.save()

        res = self.client.get("/api/v1/channels/")
        self.assertEqual(res.status_code, 200)
        slugs = [c["slug"] for c in res.json()]
        self.assertNotIn("internal_pos", slugs)
        self.assertIn("ubereats", slugs)
