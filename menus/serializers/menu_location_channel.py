from rest_framework import serializers
from menus.models import MenuLocationChannel


class MenuLocationChannelReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for nesting channels inside locations."""
    channel_name = serializers.CharField(
        source="channel_link.channel.display_name", read_only=True
    )

    class Meta:
        model = MenuLocationChannel
        fields = [
            "id", "channel_link", "channel_name",
            "status", "published_at", "published_by",
            "snapshot", "error_message",
        ]
        read_only_fields = fields


class MenuLocationChannelSerializer(serializers.ModelSerializer):
    """Write serializer for assigning channels."""
    channel_name = serializers.CharField(
        source="channel_link.channel.display_name", read_only=True
    )

    class Meta:
        model = MenuLocationChannel
        fields = [
            "id", "menu_location", "channel_link", "channel_name",
            "status", "published_at", "published_by",
            "snapshot", "error_message",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "published_at", "published_by",
            "snapshot", "error_message", "created_at", "updated_at",
        ]
