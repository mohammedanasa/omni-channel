from ..models import Product, Category


class MenuService:
    @staticmethod
    def export_menu(location, channel=None, category_id=None, visible_only=True):
        """
        Build menu data for a location, optionally filtered by category/visibility.

        Returns dict with 'products' (queryset), 'categories' (queryset), 'metadata'.
        """
        queryset = Product.objects.filter(
            product_type=Product.ProductType.MAIN,
            location_links__location=location,
            location_links__is_available=True,
        )

        if visible_only:
            queryset = queryset.filter(visible=True)

        if category_id:
            queryset = queryset.filter(categories__pos_category_id=category_id)

        categories = Category.objects.filter(
            products__in=queryset
        ).distinct()

        metadata = {
            'total_products': queryset.count(),
            'location_id': str(location.id),
            'location_name': location.name,
            'channel': channel,
        }

        return {
            'products': queryset,
            'categories': categories,
            'metadata': metadata,
        }
