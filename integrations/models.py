from django.db import models
from common.models import BaseUUIDModel


class SyncStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SYNCING = "syncing", "Syncing"
    SYNCED = "synced", "Synced"
    ERROR = "error", "Error"


class ChannelLink(BaseUUIDModel):
    """Links a Channel to a specific Location within a tenant schema."""

    channel = models.ForeignKey(
        "channels.Channel",
        on_delete=models.CASCADE,
        related_name="channel_links",
    )
    location = models.ForeignKey(
        "locations.Location",
        on_delete=models.CASCADE,
        related_name="channel_links",
    )
    credentials = models.JSONField(
        default=dict,
        blank=True,
        help_text="Encrypted credentials / API keys for this channel+location",
    )
    external_store_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The store/restaurant ID on the external platform",
    )
    is_active = models.BooleanField(default=True)
    sync_status = models.CharField(
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    sync_error = models.TextField(blank=True, default="")
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("channel", "location")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} @ {self.location}"


class ProductChannelConfig(BaseUUIDModel):
    """Per-product, per-channel configuration within a location."""

    product_location = models.ForeignKey(
        "products.ProductLocation",
        on_delete=models.CASCADE,
        related_name="channel_configs",
    )
    channel = models.ForeignKey(
        "channels.Channel",
        on_delete=models.CASCADE,
        related_name="product_channel_configs",
    )
    price = models.IntegerField(
        null=True,
        blank=True,
        help_text="Override price in cents; null = use default ProductLocation price",
    )
    is_available = models.BooleanField(default=True)
    external_product_id = models.CharField(max_length=255, blank=True, default="")
    extra_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("product_location", "channel")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product_location} → {self.channel}"
