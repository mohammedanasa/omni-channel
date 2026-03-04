from rest_framework import serializers
from .models import ChannelLink, ProductChannelConfig


class ChannelLinkSerializer(serializers.ModelSerializer):
    channel_slug = serializers.SlugRelatedField(
        source="channel", slug_field="slug", read_only=True
    )
    channel_display_name = serializers.CharField(
        source="channel.display_name", read_only=True
    )
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = ChannelLink
        fields = [
            "id",
            "channel",
            "channel_slug",
            "channel_display_name",
            "location",
            "location_name",
            "credentials",
            "external_store_id",
            "is_active",
            "sync_status",
            "sync_error",
            "last_sync_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "sync_status",
            "sync_error",
            "last_sync_at",
            "created_at",
            "updated_at",
        ]


class ProductChannelConfigSerializer(serializers.ModelSerializer):
    channel_slug = serializers.SlugRelatedField(
        source="channel", slug_field="slug", read_only=True
    )

    class Meta:
        model = ProductChannelConfig
        fields = [
            "id",
            "product_location",
            "channel",
            "channel_slug",
            "price",
            "is_available",
            "external_product_id",
            "extra_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
