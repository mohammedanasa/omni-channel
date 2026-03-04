from unittest.mock import patch, MagicMock

import requests as req_lib
from django.db import connection
from tests.base import BaseAPITest

from accounts.models import Merchant
from webhooks.dispatcher import dispatch_webhook_event
from webhooks.models import WebhookEndpoint, WebhookLog


class TestOutboundDispatch(BaseAPITest):

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        # Switch to tenant schema so webhook models are available
        self.tenant = Merchant.objects.get(id=self.merchant_id)
        connection.set_tenant(self.tenant)

        self.endpoint = WebhookEndpoint.objects.create(
            url="https://example.com/webhook",
            secret="test-secret",
            events=["order.created", "order.status_changed"],
            is_active=True,
        )

    def tearDown(self):
        connection.set_schema_to_public()

    @patch("webhooks.dispatcher.requests.post")
    def test_dispatch_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ok": true}'
        mock_post.return_value = mock_resp

        dispatch_webhook_event(
            event_type="order.created",
            payload={"order_id": "123"},
            channel_slug="internal_pos",
        )

        mock_post.assert_called_once()
        logs = WebhookLog.objects.all()
        self.assertEqual(logs.count(), 1)
        self.assertTrue(logs.first().success)

    @patch("webhooks.dispatcher.requests.post")
    def test_dispatch_skips_unsubscribed_events(self, mock_post):
        dispatch_webhook_event(
            event_type="menu.updated",
            payload={"menu_id": "456"},
        )
        mock_post.assert_not_called()

    @patch("webhooks.dispatcher.requests.post")
    def test_dispatch_includes_signature(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_post.return_value = mock_resp

        dispatch_webhook_event("order.created", {"test": True})

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        self.assertIn("X-Webhook-Signature", headers)

    @patch("webhooks.dispatcher.requests.post")
    def test_dispatch_handles_failure(self, mock_post):
        mock_post.side_effect = req_lib.ConnectionError("Connection refused")

        dispatch_webhook_event("order.created", {"test": True})

        log = WebhookLog.objects.first()
        self.assertFalse(log.success)
        self.assertIn("Connection refused", log.error_message)

    @patch("webhooks.dispatcher.requests.post")
    def test_wildcard_subscription(self, mock_post):
        self.endpoint.events = ["*"]
        self.endpoint.save()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_post.return_value = mock_resp

        dispatch_webhook_event("any.event", {"data": True})
        mock_post.assert_called_once()
