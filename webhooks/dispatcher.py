from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from webhooks.models import WebhookEndpoint, WebhookLog, WebhookDirection
from webhooks.verification import generate_hmac_signature

logger = logging.getLogger(__name__)


def dispatch_webhook_event(
    event_type: str,
    payload: dict,
    channel_slug: str = "",
    endpoint: Optional[WebhookEndpoint] = None,
) -> None:
    """
    Send an outbound webhook to all active endpoints subscribed to event_type.
    If a specific endpoint is provided, send only to that endpoint.
    """
    endpoints = (
        [endpoint]
        if endpoint
        else WebhookEndpoint.objects.filter(is_active=True)
    )

    body = json.dumps(payload, default=str)
    body_bytes = body.encode("utf-8")

    for ep in endpoints:
        if event_type not in ep.events and "*" not in ep.events:
            continue

        headers = {"Content-Type": "application/json"}
        if ep.secret:
            sig = generate_hmac_signature(body_bytes, ep.secret)
            headers["X-Webhook-Signature"] = sig

        log = WebhookLog(
            direction=WebhookDirection.OUTBOUND,
            channel_slug=channel_slug,
            event_type=event_type,
            url=ep.url,
            request_headers=headers,
            request_body=payload,
        )

        try:
            resp = requests.post(ep.url, data=body, headers=headers, timeout=10)
            log.response_status = resp.status_code
            log.response_body = resp.text[:5000]
            log.success = 200 <= resp.status_code < 300
        except requests.RequestException as e:
            log.success = False
            log.error_message = str(e)
            logger.warning("Webhook dispatch failed for %s: %s", ep.url, e)

        log.save()
