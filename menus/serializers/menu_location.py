from rest_framework import serializers
from menus.models import MenuLocation
from .menu_location_channel import MenuLocationChannelReadSerializer


class MenuLocationReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for nesting locations (with channels) inside menus."""
    location_name = serializers.CharField(source="location.name", read_only=True)
    channels = MenuLocationChannelReadSerializer(
        source="channel_publishes", many=True, read_only=True
    )

    class Meta:
        model = MenuLocation
        fields = [
            "id", "location", "location_name",
            "is_active", "channels",
        ]
        read_only_fields = fields


class MenuLocationSerializer(serializers.ModelSerializer):
    """Write serializer for assigning locations."""
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = MenuLocation
        fields = [
            "id", "menu", "location", "location_name",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
