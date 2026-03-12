from django.db import transaction
from django.utils import timezone

from menus.models import MenuLocationChannel, PublishStatus
from products.models import ProductLocation


class MenuPublisherService:

    @staticmethod
    def _resolve_price(menu_item, product_location, channel_slug):
        """Resolve price through the 5-level fallback chain."""
        # 1. Menu-level override
        if menu_item.price_override is not None:
            return menu_item.price_override

        if product_location:
            # 2-3. Channel / location price
            return product_location.get_price_for_channel(channel_slug)

        # 4-5. Handled inside get_price_for_channel, final fallback
        return menu_item.product.price

    @staticmethod
    def build_payload(menu, location, channel_link):
        """
        Build a publish-ready payload for a menu at a location+channel.
        READ-only on catalog data. Returns dict with items and metadata.
        """
        channel_slug = channel_link.channel.slug
        payload_categories = []
        skipped = []

        for cat in menu.categories.prefetch_related("items__product").order_by("sort_order"):
            cat_items = []
            for item in cat.items.filter(is_visible=True).select_related("product").order_by("sort_order"):
                product = item.product

                # Skip invisible / inactive catalog products
                if not product.visible or not product.is_active:
                    skipped.append({"plu": product.plu, "reason": "not visible/active"})
                    continue

                # Check ProductLocation exists and is available
                try:
                    pl = ProductLocation.objects.get(
                        product=product, location=location
                    )
                except ProductLocation.DoesNotExist:
                    skipped.append({"plu": product.plu, "reason": "not stocked at location"})
                    continue

                if not pl.is_available:
                    skipped.append({"plu": product.plu, "reason": "unavailable at location"})
                    continue

                if not pl.is_available_on_channel(channel_slug):
                    skipped.append({"plu": product.plu, "reason": f"unavailable on {channel_slug}"})
                    continue

                price = MenuPublisherService._resolve_price(item, pl, channel_slug)

                cat_items.append({
                    "plu": product.plu,
                    "name": product.name,
                    "description": product.description,
                    "image_url": product.image_url,
                    "price": price,
                    "sort_order": item.sort_order,
                })

            if cat_items:
                payload_categories.append({
                    "name": cat.name,
                    "sort_order": cat.sort_order,
                    "items": cat_items,
                })

        availabilities = []
        for avail in menu.availabilities.all():
            availabilities.append({
                "day_of_week": avail.day_of_week,
                "start_time": str(avail.start_time),
                "end_time": str(avail.end_time),
                "start_date": str(avail.start_date) if avail.start_date else None,
                "end_date": str(avail.end_date) if avail.end_date else None,
            })

        return {
            "menu_name": menu.name,
            "location_id": str(location.id),
            "location_name": location.name,
            "channel": channel_slug,
            "categories": payload_categories,
            "availabilities": availabilities,
            "skipped": skipped,
        }

    @staticmethod
    @transaction.atomic
    def publish(menu_location_channel, user=None):
        """
        Build payload and push to channel via adapter.
        Updates MenuLocationChannel with status and snapshot.
        """
        mlc = menu_location_channel
        menu = mlc.menu_location.menu
        location = mlc.menu_location.location
        channel_link = mlc.channel_link

        payload = MenuPublisherService.build_payload(menu, location, channel_link)

        try:
            from integrations.adapters import AdapterRegistry

            adapter = AdapterRegistry.get_adapter(channel_link)
            adapter.push_menu(payload)

            mlc.status = PublishStatus.PUBLISHED
            mlc.error_message = ""
        except Exception as exc:
            mlc.status = PublishStatus.FAILED
            mlc.error_message = str(exc)

        mlc.published_at = timezone.now()
        mlc.published_by = user
        mlc.snapshot = payload
        mlc.save()

        return mlc

    @staticmethod
    def publish_menu(menu, user=None):
        """Publish a menu to ALL its assigned location-channels."""
        results = []
        mlcs = MenuLocationChannel.objects.filter(
            menu_location__menu=menu,
            menu_location__is_active=True,
        ).select_related(
            "menu_location__menu",
            "menu_location__location",
            "channel_link__channel",
        )
        for mlc in mlcs:
            result = MenuPublisherService.publish(mlc, user=user)
            results.append(result)
        return results
