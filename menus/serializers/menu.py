from rest_framework import serializers
from menus.models import Menu
from .menu_category import MenuCategoryReadSerializer
from .menu_availability import MenuAvailabilityReadSerializer
from .menu_location import MenuLocationReadSerializer


class MenuSerializer(serializers.ModelSerializer):
    categories = MenuCategoryReadSerializer(many=True, read_only=True)
    availabilities = MenuAvailabilityReadSerializer(many=True, read_only=True)
    locations = MenuLocationReadSerializer(
        source="menu_locations", many=True, read_only=True
    )

    class Meta:
        model = Menu
        fields = [
            "id", "name", "description", "image_url",
            "is_active", "sort_order",
            "categories", "availabilities", "locations",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
