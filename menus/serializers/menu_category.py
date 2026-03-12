from rest_framework import serializers
from menus.models import MenuCategory
from .menu_item import MenuItemReadSerializer


class MenuCategoryReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for nesting categories (with items) inside menus."""
    items = MenuItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = [
            "id", "name", "description", "image_url",
            "sort_order", "items",
        ]
        read_only_fields = fields


class MenuCategorySerializer(serializers.ModelSerializer):
    """Write serializer for creating/updating categories."""

    class Meta:
        model = MenuCategory
        fields = [
            "id", "menu", "name", "description", "image_url",
            "sort_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        menu = attrs.get("menu") or self.instance.menu
        name = attrs.get("name") or (self.instance.name if self.instance else None)
        qs = MenuCategory.objects.filter(menu=menu, name=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"name": f"Category '{name}' already exists in this menu."}
            )
        return attrs
