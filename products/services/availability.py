from django.db import transaction

from ..models import Product, ProductLocation


class AvailabilityService:
    @staticmethod
    @transaction.atomic
    def mark_unavailable(plus=None, tags=None, location=None, channel=None):
        """
        Mark products unavailable at 3 scope levels.

        Scope 1 (global): no location → Product.visible = False
        Scope 2 (location): location only → ProductLocation.is_available = False
        Scope 3 (channel): location + channel → channels[ch]['is_available'] = False

        Returns dict with 'updated' count and 'scope' description.
        """
        queryset = Product.objects.all()
        if plus:
            queryset = queryset.filter(plu__in=plus)
        elif tags:
            queryset = queryset.filter(product_tags__overlap=tags)

        # Scope 3: Location + Channel
        if location and channel:
            updated = 0
            for product in queryset:
                try:
                    pl = ProductLocation.objects.get(product=product, location=location)
                    if not pl.channels:
                        pl.channels = {}
                    if channel not in pl.channels:
                        pl.channels[channel] = {}
                    pl.channels[channel]['is_available'] = False
                    pl.save()
                    updated += 1
                except ProductLocation.DoesNotExist:
                    pass

            return {
                'updated': updated,
                'scope': f'channel {channel} at {location.name}',
            }

        # Scope 2: Location only
        if location:
            updated = ProductLocation.objects.filter(
                product__in=queryset,
                location=location,
            ).update(is_available=False)

            return {
                'updated': updated,
                'scope': f'location {location.name}',
            }

        # Scope 1: Global
        updated = queryset.update(visible=False)
        return {
            'updated': updated,
            'scope': 'global',
        }
