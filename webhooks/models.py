from django.db import models
from accounts.models import BaseUUIDModel


class WebhookDirection(models.TextChoices):
    INBOUND = "inbound", "Inbound"
    OUTBOUND = "outbound", "Outbound"


class WebhookEndpoint(BaseUUIDModel):
    """Outbound webhook endpoint registered by the tenant."""

    url = models.URLField()
    secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="HMAC secret for signing outbound payloads",
    )
    events = models.JSONField(
        default=list,
        help_text='List of event types to subscribe to, e.g. ["order.created", "order.status_changed"]',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Webhook → {self.url}"


class WebhookLog(BaseUUIDModel):
    direction = models.CharField(
        max_length=10,
        choices=WebhookDirection.choices,
    )
    channel_slug = models.CharField(max_length=50, blank=True, default="")
    event_type = models.CharField(max_length=100, blank=True, default="")
    url = models.URLField(blank=True, default="")

    request_headers = models.JSONField(default=dict, blank=True)
    request_body = models.JSONField(default=dict, blank=True)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default="")

    success = models.BooleanField(default=False)
    attempts = models.IntegerField(default=1)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.direction} {self.event_type} ({self.created_at})"
