from django.db import transaction

from ..models import Product, ProductLocation


class ProductService:
    @staticmethod
    def auto_assign_location(product, location):
        """
        Assign product to location if it has no existing assignments.
        Called after product creation when X-Location-ID header is present.
        """
        if not ProductLocation.objects.filter(product=product).exists():
            ProductLocation.objects.create(
                product=product,
                location=location,
                is_available=True,
            )

    @staticmethod
    @transaction.atomic
    def bulk_delete(plus):
        """
        Delete multiple products by PLU codes.

        Returns dict with 'deleted' count and 'not_found' list.
        """
        products = Product.objects.filter(plu__in=plus)
        found_plus = set(products.values_list('plu', flat=True))
        not_found = [plu for plu in plus if plu not in found_plus]

        deleted_count, _ = products.delete()

        return {
            'deleted': deleted_count,
            'not_found': not_found,
        }
