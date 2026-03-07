from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import TaxRate, ProductLocation


class PricingService:
    @staticmethod
    @transaction.atomic
    def update_location_pricing(product, location, data):
        """
        Update pricing, availability, stock, and tax overrides for a product at a location.

        Args:
            product: Product instance
            location: Location instance
            data: dict of fields to update

        Returns:
            dict with all updated field values

        Raises:
            ProductLocation.DoesNotExist: if product not assigned to location
            ValidationError: if any tax rate ID is invalid
        """
        pl = ProductLocation.objects.get(product=product, location=location)

        # Validate tax rate IDs before applying changes
        tax_rate_fields = [
            'delivery_tax_rate_override_id',
            'takeaway_tax_rate_override_id',
            'eat_in_tax_rate_override_id',
        ]
        errors = {}
        for field_name in tax_rate_fields:
            if field_name in data:
                tax_rate_id = data[field_name]
                if tax_rate_id is not None:
                    if not TaxRate.objects.filter(id=tax_rate_id).exists():
                        errors[field_name] = f'Tax rate with ID "{tax_rate_id}" does not exist.'

        if errors:
            raise ValidationError(errors)

        # Update fields
        updatable_fields = [
            'is_available',
            'price_override',
            'channels',
            'stock_quantity',
            'low_stock_threshold',
            'delivery_tax_rate_override_id',
            'takeaway_tax_rate_override_id',
            'eat_in_tax_rate_override_id',
        ]
        for field in updatable_fields:
            if field in data:
                setattr(pl, field, data[field])

        pl.save()

        return {
            'location_id': str(location.id),
            'location_name': location.name,
            'is_available': pl.is_available,
            'price_override': pl.price_override,
            'channels': pl.channels,
            'stock_quantity': pl.stock_quantity,
            'low_stock_threshold': pl.low_stock_threshold,
            'delivery_tax_rate_override_id': str(pl.delivery_tax_rate_override_id) if pl.delivery_tax_rate_override_id else None,
            'takeaway_tax_rate_override_id': str(pl.takeaway_tax_rate_override_id) if pl.takeaway_tax_rate_override_id else None,
            'eat_in_tax_rate_override_id': str(pl.eat_in_tax_rate_override_id) if pl.eat_in_tax_rate_override_id else None,
        }
