from django.db import models
from common.models import BaseUUIDModel


class ChannelType(models.TextChoices):
    MARKETPLACE = "marketplace", "Marketplace"
    POS = "pos", "POS"
    DIRECT = "direct", "Direct"
    CUSTOM = "custom", "Custom"


class ChannelDirection(models.TextChoices):
    INBOUND = "inbound", "Inbound"
    OUTBOUND = "outbound", "Outbound"
    BIDIRECTIONAL = "bidirectional", "Bidirectional"


class Channel(BaseUUIDModel):
    slug = models.SlugField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    channel_type = models.CharField(
        max_length=20,
        choices=ChannelType.choices,
        default=ChannelType.MARKETPLACE,
    )
    direction = models.CharField(
        max_length=20,
        choices=ChannelDirection.choices,
        default=ChannelDirection.BIDIRECTIONAL,
    )
    adapter_class = models.CharField(
        max_length=255,
        help_text="Dotted Python path to the adapter class, e.g. integrations.adapters.internal.InternalPOSAdapter",
    )
    config_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON Schema describing required credential fields for this channel",
    )
    is_active = models.BooleanField(default=True)
    icon_url = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name
