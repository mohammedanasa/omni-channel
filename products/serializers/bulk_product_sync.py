
from rest_framework import serializers
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ..models import (
    Product,
    Category,
    TaxRate,
    ProductLocation
)

from .product import ProductSerializer
from .category import CategorySerializer
from .tax_rate import TaxRateSerializer
from .location_assignment import LocationAssignmentDetailSerializer

class BulkProductSyncSerializer(serializers.Serializer):
    """
    Bulk import/sync serializer for products, categories, and tax rates.
    
    Purpose: Efficiently import large datasets from POS or external systems.
    
    Features:
    - Atomic transaction (all or nothing)
    - Update or create (upsert) logic
    - Processes tax rates first (for product references)
    - Processes categories second (for product references)
    - Processes products last
    - Re-cascades locations after all products created
    
    Fields:
    - tax_rates: List of TaxRate data (optional)
    - categories: List of Category data (optional)
    - products: List of Product data (required)
    
    Examples:
        >>> data = {
        ...     "tax_rates": [
        ...         {"name": "VAT 9%", "percentage": 9000}
        ...     ],
        ...     "categories": [
        ...         {"pos_category_id": "BURGERS", "name": "Burgers"}
        ...     ],
        ...     "products": [
        ...         {
        ...             "name": "Cheeseburger",
        ...             "product_type": 1,
        ...             "price": 899,
        ...             "pos_category_ids": ["BURGERS"]
        ...         }
        ...     ]
        ... }
        >>> serializer = BulkProductSyncSerializer(data=data)
        >>> serializer.is_valid()
        >>> result = serializer.save()
        >>> print(result)
        {
            "products": [<Product>, ...],
            "categories_count": 1,
            "tax_rates_count": 1
        }
    """
    
    # ========== FIELDS ==========
    
    products = ProductSerializer(
        many=True,
        help_text="List of products to sync"
    )
    
    categories = CategorySerializer(
        many=True,
        required=False,
        help_text="List of categories to sync (optional)"
    )
    
    tax_rates = TaxRateSerializer(
        many=True,
        required=False,
        help_text="List of tax rates to sync (optional)"
    )
    
    # ========== METHODS ==========
    
    @transaction.atomic
    def create(self, validated_data):
        """
        Process bulk sync in correct order.
        
        Order:
        1. Tax rates (so products can reference them)
        2. Categories (so products can reference them)
        3. Products (can now reference tax rates and categories)
        4. Re-cascade locations (ensures all relationships exist first)
        
        Logic: Update if exists (by name/PLU), create if new.
        
        Args:
            validated_data (dict): Validated data
            
        Returns:
            dict: Result summary with counts and objects
            
        Raises:
            Exception: Any error rolls back entire transaction
        """
        # Process tax rates
        tax_rates_data = validated_data.get('tax_rates', [])
        for tr_data in tax_rates_data:
            TaxRate.objects.update_or_create(
                name=tr_data['name'],
                defaults={
                    'percentage': tr_data.get('percentage'),
                    'flat_fee': tr_data.get('flat_fee'),
                    'description': tr_data.get('description', ''),
                    'is_default': tr_data.get('is_default', False),
                    'is_active': tr_data.get('is_active', True),
                }
            )
        
        # Process categories
        categories_data = validated_data.get('categories', [])
        for cat_data in categories_data:
            Category.objects.update_or_create(
                pos_category_id=cat_data['pos_category_id'],
                defaults={
                    'name': cat_data['name'],
                    'image_url': cat_data.get('image_url', ''),
                    'description': cat_data.get('description', ''),
                    'name_translations': cat_data.get('name_translations', {}),
                    'description_translations': cat_data.get('description_translations', {}),
                    'sort_order': cat_data.get('sort_order', 0),
                }
            )
        
        # Process products
        products_data = validated_data.get('products', [])
        created_products = []
        
        for product_data in products_data:
            serializer = ProductSerializer(context=self.context)
            
            # Check if PLU exists
            plu = product_data.get('plu')
            if plu and Product.objects.filter(plu=plu).exists():
                # Update existing
                product = Product.objects.get(plu=plu)
                serializer.update(product, product_data)
            else:
                # Create new
                product = serializer.create(product_data)
            
            created_products.append(product)
        
        # ⭐ NEW: Re-cascade ALL products after creation
        # This ensures cascading works even when sub-products created after parent
        self._recascade_all_products(created_products)
        
        return {
            'products': created_products,
            'categories_count': len(categories_data),
            'tax_rates_count': len(tax_rates_data)
        }
    
    def _recascade_all_products(self, products):
        """
        Re-cascade locations for all products after creation.
        
        This ensures cascading works correctly even when products
        are created in any order.
        
        Process:
        1. For each product with location assignments
        2. Cascade those assignments to all sub-products recursively
        
        Args:
            products (list): List of created Product instances
        """
        for product in products:
            # Get location assignments for this product
            location_links = ProductLocation.objects.filter(product=product)
            
            if not location_links.exists():
                continue
            
            # Convert to assignment format for cascading
            location_assignments = [
                {
                    'location_id': str(pl.location_id),
                    'is_available': pl.is_available,
                    'price_override': pl.price_override,
                    'channels': pl.channels,
                    'stock_quantity': pl.stock_quantity,
                    'delivery_tax_rate_override_id': pl.delivery_tax_rate_override_id,
                    'takeaway_tax_rate_override_id': pl.takeaway_tax_rate_override_id,
                    'eat_in_tax_rate_override_id': pl.eat_in_tax_rate_override_id,
                }
                for pl in location_links
            ]
            
            # Cascade to all sub-products
            self._cascade_to_children(product, location_assignments)
    
    def _cascade_to_children(self, product, location_assignments):
        """
        Recursively cascade locations to all sub-products.
        
        Args:
            product (Product): Parent product
            location_assignments (list): Location assignment data
        """
        if not location_assignments:
            return
        
        # Get sub-products (all should exist now)
        sub_products = product.sub_products.all()
        
        if not sub_products.exists():
            return
        
        from locations.models import Location
        
        # Get location objects
        location_ids = [la['location_id'] for la in location_assignments]
        locations = Location.objects.filter(id__in=location_ids)
        location_map = {str(loc.id): loc for loc in locations}
        
        for sub_product in sub_products:
            # Clear existing assignments for sub-product
            ProductLocation.objects.filter(product=sub_product).delete()
            
            # Create new assignments (same as parent)
            for assignment in location_assignments:
                location = location_map[str(assignment['location_id'])]
                
                ProductLocation.objects.create(
                    product=sub_product,
                    location=location,
                    is_available=assignment.get('is_available', True),
                    price_override=assignment.get('price_override'),
                    channels=assignment.get('channels', {}),
                    stock_quantity=assignment.get('stock_quantity'),
                    delivery_tax_rate_override_id=assignment.get('delivery_tax_rate_override_id'),
                    takeaway_tax_rate_override_id=assignment.get('takeaway_tax_rate_override_id'),
                    eat_in_tax_rate_override_id=assignment.get('eat_in_tax_rate_override_id'),
                )
            
            # Recurse to this sub-product's children
            self._cascade_to_children(sub_product, location_assignments)

