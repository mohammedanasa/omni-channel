from django.contrib import admin
from .models import ChannelLink, ProductChannelConfig


@admin.register(ChannelLink)
class ChannelLinkAdmin(admin.ModelAdmin):
    list_display = [
        "channel",
        "location",
        "external_store_id",
        "is_active",
        "sync_status",
        "last_sync_at",
    ]
    list_filter = ["is_active", "sync_status", "channel"]
    search_fields = ["external_store_id"]


@admin.register(ProductChannelConfig)
class ProductChannelConfigAdmin(admin.ModelAdmin):
    list_display = ["product_location", "channel", "price", "is_available"]
    list_filter = ["is_available", "channel"]
