from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from menus.models import MenuItem


class MenuItemReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for nesting items inside categories."""
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_plu = serializers.CharField(source="product.plu", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id", "product", "product_name", "product_plu",
            "sort_order", "price_override", "is_visible",
        ]
        read_only_fields = fields


class MenuItemSerializer(serializers.ModelSerializer):
    """Write serializer for creating/updating items."""
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_plu = serializers.CharField(source="product.plu", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id", "menu_category", "product", "product_name", "product_plu",
            "sort_order", "price_override", "is_visible",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        menu_category = attrs.get("menu_category") or self.instance.menu_category
        product = attrs.get("product") or self.instance.product
        menu = menu_category.menu
        qs = MenuItem.objects.filter(menu_category__menu=menu, product=product)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"product": f"Product '{product.name}' is already in menu '{menu.name}'."}
            )
        return attrs
