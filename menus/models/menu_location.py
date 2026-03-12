from django.db import models
from common.models import BaseUUIDModel
from .menu import Menu


class MenuLocation(BaseUUIDModel):
    """Assigns a menu to a location."""

    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="menu_locations")
    location = models.ForeignKey(
        "locations.Location", on_delete=models.CASCADE, related_name="menu_locations"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("menu", "location")

    def __str__(self):
        return f"{self.menu.name} @ {self.location.name}"
