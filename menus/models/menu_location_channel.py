from django.db import models
from django.conf import settings
from common.models import BaseUUIDModel
from .menu_location import MenuLocation


class PublishStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"


class MenuLocationChannel(BaseUUIDModel):
    """Tracks publish state of a menu at a location to a specific channel."""

    menu_location = models.ForeignKey(
        MenuLocation, on_delete=models.CASCADE, related_name="channel_publishes"
    )
    channel_link = models.ForeignKey(
        "integrations.ChannelLink",
        on_delete=models.CASCADE,
        related_name="menu_publishes",
    )
    status = models.CharField(
        max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    snapshot = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("menu_location", "channel_link")

    def __str__(self):
        return f"{self.menu_location} → {self.channel_link.channel} [{self.status}]"
