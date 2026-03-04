import json
from tests.base import BaseAPITest
from channels.models import Channel
from integrations.models import ChannelLink
from locations.models import Location


class TestInboundWebhook(BaseAPITest):

    def test_inbound_webhook_resolves_tenant(self):
        user, pwd, merchant_id = self.setup_user_and_merchant()
        location_id = self.create_location(merchant_id)
        channel = self.create_channel()
        link_id = self.create_channel_link(channel, location_id, merchant_id)

        # Hit inbound webhook — no auth headers, no tenant header
        self.client.credentials()  # remove JWT
        res = self.client.post(
            f"/api/v1/webhooks/inbound/{link_id}/",
            data=json.dumps({"event_type": "test", "data": {}}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

    def test_inbound_webhook_invalid_link_id(self):
        import uuid
        self.client.credentials()
        res = self.client.post(
            f"/api/v1/webhooks/inbound/{uuid.uuid4()}/",
            data=json.dumps({"event_type": "test"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 404)
