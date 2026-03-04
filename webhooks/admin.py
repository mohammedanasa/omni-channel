from django.contrib import admin
from .models import WebhookEndpoint, WebhookLog


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ["url", "is_active", "events", "created_at"]
    list_filter = ["is_active"]


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = [
        "direction", "channel_slug", "event_type",
        "success", "response_status", "created_at",
    ]
    list_filter = ["direction", "success", "channel_slug"]
    readonly_fields = [
        "direction", "channel_slug", "event_type", "url",
        "request_headers", "request_body", "response_status",
        "response_body", "success", "attempts", "error_message",
    ]
