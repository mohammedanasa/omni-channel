from django.db import models
from django.core.exceptions import ValidationError
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

    def save(self, *args, **kwargs):
        self._enforce_single_pos_per_location()
        super().save(*args, **kwargs)

    def _enforce_single_pos_per_location(self):
        """Ensure at most one active POS-type channel link per location."""
        if not self.is_active:
            return
        if self.channel.channel_type != "pos":
            return

        conflict = (
            ChannelLink.objects.filter(
                location=self.location,
                channel__channel_type="pos",
                is_active=True,
            )
            .exclude(pk=self.pk)
            .select_related("channel")
            .first()
        )
        if conflict:
            raise ValidationError(
                f"Only one active POS per location is allowed. "
                f"Deactivate '{conflict.channel.display_name}' at "
                f"'{self.location}' first."
            )


class ProductChannelConfig(BaseUUIDModel):
    """
    Per-product, per-channel configuration within a location.

    This model is the admin/API-facing interface for channel-specific
    pricing and availability. On save, it writes through to
    ProductLocation.channels JSONField to maintain a single source of
    truth for price/availability resolution.
    """

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Write-through to ProductLocation.channels for single source of truth
        self._sync_to_product_location()

    def delete(self, *args, **kwargs):
        pl = self.product_location
        channel_slug = self.channel.slug
        super().delete(*args, **kwargs)
        # Remove channel data from ProductLocation.channels
        if pl.channels and channel_slug in pl.channels:
            del pl.channels[channel_slug]
            pl.save(update_fields=["channels"])

    def _sync_to_product_location(self):
        """Sync price and availability to ProductLocation.channels JSONField."""
        pl = self.product_location
        pl.set_channel_data(
            self.channel.slug,
            price=self.price,
            is_available=self.is_available,
        )
        pl.save(update_fields=["channels"])
