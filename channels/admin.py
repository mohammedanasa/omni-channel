from django.contrib import admin
from .models import Channel


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ["slug", "display_name", "channel_type", "direction", "is_active"]
    list_filter = ["channel_type", "direction", "is_active"]
    search_fields = ["slug", "display_name"]
    prepopulated_fields = {"slug": ("display_name",)}
