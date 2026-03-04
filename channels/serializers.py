from rest_framework import serializers
from .models import Channel


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = [
            "id",
            "slug",
            "display_name",
            "channel_type",
            "direction",
            "adapter_class",
            "config_schema",
            "is_active",
            "icon_url",
        ]
        read_only_fields = ["id"]
