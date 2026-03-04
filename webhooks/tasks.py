from __future__ import annotations

import json
import logging

import requests
from celery import shared_task

from webhooks.verification import generate_hmac_signature

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_BACKOFF = 60  # base seconds; actual = RETRY_BACKOFF * 2^retries


@shared_task(bind=True, max_retries=MAX_RETRIES, default_retry_delay=RETRY_BACKOFF)
def dispatch_webhook_async(
    self,
    webhook_endpoint_id: str,
    event_type: str,
    payload: dict,
    channel_slug: str = "",
    schema_name: str = "public",
) -> None:
    """
    Async webhook dispatch with exponential backoff.
    Runs inside Celery; switches to the correct tenant schema.
    """
    from django.db import connection
    from django_tenants.utils import get_tenant_model

    from webhooks.models import WebhookEndpoint, WebhookLog, WebhookDirection

    # Switch schema
    if schema_name != "public":
        TenantModel = get_tenant_model()
        try:
            tenant = TenantModel.objects.get(schema_name=schema_name)
            connection.set_tenant(tenant)
        except TenantModel.DoesNotExist:
            logger.error("Tenant schema %s not found", schema_name)
            return

    try:
        ep = WebhookEndpoint.objects.get(id=webhook_endpoint_id, is_active=True)
    except WebhookEndpoint.DoesNotExist:
        logger.info("WebhookEndpoint %s not found or inactive", webhook_endpoint_id)
        return

    body = json.dumps(payload, default=str)
    body_bytes = body.encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if ep.secret:
        headers["X-Webhook-Signature"] = generate_hmac_signature(body_bytes, ep.secret)

    log = WebhookLog(
        direction=WebhookDirection.OUTBOUND,
        channel_slug=channel_slug,
        event_type=event_type,
        url=ep.url,
        request_headers=headers,
        request_body=payload,
        attempts=self.request.retries + 1,
    )

    try:
        resp = requests.post(ep.url, data=body, headers=headers, timeout=10)
        log.response_status = resp.status_code
        log.response_body = resp.text[:5000]
        log.success = 200 <= resp.status_code < 300

        if not log.success:
            log.error_message = f"HTTP {resp.status_code}"
    except requests.RequestException as e:
        log.success = False
        log.error_message = str(e)

    log.save()

    if not log.success:
        raise self.retry(
            countdown=RETRY_BACKOFF * (2 ** self.request.retries),
            exc=Exception(log.error_message),
        )

    connection.set_schema_to_public()


@shared_task
def check_sync_health() -> None:
    """Periodic task: flag stale channel links that haven't synced recently."""
    from datetime import timedelta

    from django.db import connection
    from django.utils import timezone
    from django_tenants.utils import get_tenant_model

    from integrations.models import ChannelLink, SyncStatus

    TenantModel = get_tenant_model()
    stale_threshold = timezone.now() - timedelta(hours=24)

    for tenant in TenantModel.objects.exclude(schema_name="public"):
        connection.set_tenant(tenant)
        stale = ChannelLink.objects.filter(
            is_active=True,
            sync_status=SyncStatus.SYNCED,
            last_sync_at__lt=stale_threshold,
        )
        count = stale.update(sync_status=SyncStatus.PENDING)
        if count:
            logger.info(
                "Tenant %s: marked %d channel links as pending (stale sync)",
                tenant.schema_name,
                count,
            )

    connection.set_schema_to_public()
