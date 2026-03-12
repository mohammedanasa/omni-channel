from django.db import models
from common.models import BaseUUIDModel
from .menu import Menu


class MenuCategory(BaseUUIDModel):
    """Customer-facing category within a menu."""

    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, max_length=500)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("menu", "name")
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Menu categories"

    def __str__(self):
        return f"{self.menu.name} / {self.name}"
