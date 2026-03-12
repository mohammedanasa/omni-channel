"""
Management command to seed the Channel table with built-in integrations.

Usage:
    python manage.py seed_channels
"""

from django.core.management.base import BaseCommand

from channels.models import Channel, ChannelType, ChannelDirection


CHANNELS = [
    {
        "slug": "internal_pos",
        "display_name": "Internal POS",
        "channel_type": ChannelType.POS,
        "direction": ChannelDirection.BIDIRECTIONAL,
        "adapter_class": "integrations.adapters.internal.InternalPOSAdapter",
        "config_schema": {},
    },
    {
        "slug": "deliveroo",
        "display_name": "Deliveroo",
        "channel_type": ChannelType.MARKETPLACE,
        "direction": ChannelDirection.BIDIRECTIONAL,
        "adapter_class": "integrations.adapters.deliveroo.DeliverooAdapter",
        "config_schema": {
            "type": "object",
            "required": ["client_id", "client_secret", "brand_id", "site_id"],
            "properties": {
                "client_id": {"type": "string", "description": "OAuth2 client ID from Deliveroo Developer Portal"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
                "brand_id": {"type": "string", "description": "Brand ID from Deliveroo"},
                "site_id": {"type": "string", "description": "Site/store ID on Deliveroo"},
                "menu_id": {"type": "string", "description": "Menu ID (auto-populated after first push)"},
                "webhook_secret": {"type": "string", "description": "HMAC secret for webhook verification"},
                "environment": {
                    "type": "string",
                    "enum": ["sandbox", "production"],
                    "default": "sandbox",
                    "description": "API environment",
                },
            },
        },
    },
    {
        "slug": "ubereats",
        "display_name": "Uber Eats",
        "channel_type": ChannelType.MARKETPLACE,
        "direction": ChannelDirection.BIDIRECTIONAL,
        "adapter_class": "",  # Stub — adapter not yet implemented
        "config_schema": {},
    },
    {
        "slug": "doordash",
        "display_name": "DoorDash",
        "channel_type": ChannelType.MARKETPLACE,
        "direction": ChannelDirection.BIDIRECTIONAL,
        "adapter_class": "",
        "config_schema": {},
    },
    {
        "slug": "square",
        "display_name": "Square",
        "channel_type": ChannelType.POS,
        "direction": ChannelDirection.BIDIRECTIONAL,
        "adapter_class": "",
        "config_schema": {},
    },
    {
        "slug": "toast",
        "display_name": "Toast",
        "channel_type": ChannelType.POS,
        "direction": ChannelDirection.BIDIRECTIONAL,
        "adapter_class": "",
        "config_schema": {},
    },
]


class Command(BaseCommand):
    help = "Seed the Channel table with built-in integrations"

    def handle(self, *args, **options):
        for data in CHANNELS:
            obj, created = Channel.objects.update_or_create(
                slug=data["slug"],
                defaults=data,
            )
            status = "created" if created else "updated"
            self.stdout.write(f"  {status}: {obj.display_name} ({obj.slug})")

        self.stdout.write(self.style.SUCCESS(f"\nSeeded {len(CHANNELS)} channels."))
