from django.db import models
from django.core.validators import MinValueValidator
from common.models import BaseUUIDModel
from .menu_category import MenuCategory


class MenuItem(BaseUUIDModel):
    """A product selected into a menu under a specific category."""

    menu_category = models.ForeignKey(
        MenuCategory, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="menu_items"
    )
    sort_order = models.IntegerField(default=0)
    price_override = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Menu-specific price in cents. Null = use catalog/location price.",
    )
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.product.name} in {self.menu_category}"

    def clean(self):
        """Ensure a product appears only once per menu (across all categories)."""
        from django.core.exceptions import ValidationError

        menu = self.menu_category.menu
        qs = MenuItem.objects.filter(
            menu_category__menu=menu, product=self.product
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                f"Product '{self.product.name}' is already in menu '{menu.name}'."
            )
