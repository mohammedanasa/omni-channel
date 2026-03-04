from rest_framework import serializers
from .models import WebhookEndpoint, WebhookLog


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = ["id", "url", "secret", "events", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "secret": {"write_only": True},
        }


class WebhookLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookLog
        fields = [
            "id", "direction", "channel_slug", "event_type", "url",
            "request_headers", "request_body", "response_status",
            "response_body", "success", "attempts", "next_retry_at",
            "error_message", "created_at",
        ]
        read_only_fields = fields
