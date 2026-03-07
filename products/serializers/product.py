"""
==============================================================================
PRODUCTS SERIALIZERS - COMPREHENSIVE DOCUMENTATION
==============================================================================

This module contains all DRF serializers for the product management system.

Serializers:
    - TaxRateSerializer: Tax rate CRUD with validation
    - CategorySerializer: Category CRUD with product count
    - LocationAssignmentDetailSerializer: Read-only location details
    - LocationAssignmentSerializer: Write-only location assignments
    - ProductSerializer: Main product serializer with full features
    - NestedProductSerializer: Recursive serializer for menu export
    - BulkProductSyncSerializer: Bulk import/sync operations

Key Features:
    - Auto-generated PLU support
    - Location/channel context handling
    - Tax rate validation (percentage XOR flat_fee)
    - Circular reference detection
    - Nested product structures
    - Expand parameter support
    - Backward compatibility

Usage Examples:
    # Create product
    serializer = ProductSerializer(data=request.data)
    if serializer.is_valid():
        product = serializer.save()
    
    # Get product with location context
    serializer = ProductSerializer(
        product,
        context={'location': location, 'channel': 'ubereats'}
    )
    
    # Export nested menu
    serializer = NestedProductSerializer(
        products,
        many=True,
        context={'location': location, 'max_depth': 10}
    )

Author: Your Team
Version: 1.0.0
"""

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ..models import (
    Product,
    Category,
    TaxRate,
    ProductRelation,
    ProductLocation
)

from .location_assignment import LocationAssignmentSerializer, LocationAssignmentDetailSerializer
from .category import CategorySerializer
from .tax_rate import TaxRateSerializer



# Keep all your existing serializers (CategorySerializer, TaxRateSerializer, etc.)
# I'm showing only the UPDATED serializers:

class ProductSerializer(serializers.ModelSerializer):
    """
    Universal product serializer with full features.
    
    Features:
    - Auto-generated PLU (if not provided)
    - Location/channel context handling
    - Tax rate references with validation
    - Sub-product relationships (PLU-based)
    - Category assignments (pos_category_id-based)
    - Location assignments with channel pricing
    - Circular reference detection
    - Effective price calculation
    - Dynamic location display logic
    
    Context Variables (from request):
    - location: Location instance (from X-Location-ID header)
    - channel: Channel name string (from X-Channel header)
    - expand: List of fields to expand
    
    Location Display Logic:
    - WITHOUT location header: Shows 'locations' (all assignments)
    - WITH location header: Shows 'current_location_info' (specific location)
    
    Read/Write Fields:
    - locations: Accepts LocationAssignment data on write,
                 returns full location details on read
    
    Write Fields (input only):
    - pos_category_ids: List of category IDs
    - sub_products: List of PLUs for sub-products
    - delivery_tax_rate_id, takeaway_tax_rate_id, eat_in_tax_rate_id
    
    Read Fields (output only):
    - categories: Full category objects
    - current_location_info: Current location data (when header present)
    - effective_price: Calculated price with overrides
    - sub_products: List of sub-product PLUs
    - delivery_tax_rate, takeaway_tax_rate, eat_in_tax_rate: Full objects
    
    Examples:
        >>> # Create product without PLU (auto-generated)
        >>> data = {
        ...     "name": "Cheeseburger",
        ...     "product_type": 1,
        ...     "price": 899,
        ...     "pos_category_ids": ["BURGERS"],
        ...     "locations": [{
        ...         "location_id": "uuid",
        ...         "price_override": 999,
        ...         "channels": {
        ...             "ubereats": {"price": 1099, "is_available": True}
        ...         }
        ...     }]
        ... }
        >>> serializer = ProductSerializer(data=data)
        >>> serializer.is_valid()
        >>> product = serializer.save()
        >>> print(product.plu)  # "MAIN-CHEESE-A7B9"
        
        >>> # Get product with location context
        >>> serializer = ProductSerializer(
        ...     product,
        ...     context={
        ...         'request': request,
        ...         'location': location,
        ...         'channel': 'ubereats'
        ...     }
        ... )
        >>> print(serializer.data['effective_price'])  # 1099
        >>> print(serializer.data['current_location_info'])
        {
            "location_id": "uuid",
            "location_name": "NYC",
            "is_available": true,
            "effective_price": 1099,
            ...
        }
    """
    
    # ========== WRITE-ONLY FIELDS ==========
    
    pos_category_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True,
        help_text="""
        List of category pos_category_id values.
        Used to assign product to categories.
        Example: ["BURGERS", "FEATURED"]
        """
    )
    
    sub_product_plu_list = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True,
        help_text="""
        List of PLU codes for sub-products.
        Order matters (defines sort_order).
        Example: ["GRP-TOPPIN-A1B2", "GRP-SIZES-C3D4"]
        """
    )
    
    locations = LocationAssignmentSerializer(
        many=True,
        required=False,
        write_only=True,
        help_text="Location assignments with pricing/availability data. On read, returns full location details via to_representation()."
    )
    
    # Tax rate IDs for writing
    delivery_tax_rate_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="UUID of delivery tax rate to assign"
    )
    
    takeaway_tax_rate_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="UUID of takeaway tax rate to assign"
    )
    
    eat_in_tax_rate_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="UUID of eat-in tax rate to assign"
    )
    
    # ========== READ-ONLY FIELDS ==========
    
    sub_products = serializers.SerializerMethodField(
        help_text="List of sub-product PLUs in sort order"
    )
    
    categories = CategorySerializer(
        many=True,
        read_only=True,
        help_text="Full category objects"
    )
    
    # Tax rate objects for reading
    delivery_tax_rate = TaxRateSerializer(
        read_only=True,
        help_text="Full delivery tax rate object"
    )
    
    takeaway_tax_rate = TaxRateSerializer(
        read_only=True,
        help_text="Full takeaway tax rate object"
    )
    
    eat_in_tax_rate = TaxRateSerializer(
        read_only=True,
        help_text="Full eat-in tax rate object"
    )
    
    # Location information (dynamic based on header)
    current_location_info = serializers.SerializerMethodField(
        help_text="Current location details (shown when X-Location-ID header present)"
    )
    
    # Computed fields
    effective_price = serializers.SerializerMethodField(
        help_text="Calculated price with location/channel overrides"
    )
    
    # ========== META ==========
    
    class Meta:
        model = Product
        fields = [
            # IDs
            'id', 'plu', 'pos_product_id', 'gtin',
            
            # Basic info
            'name', 'name_translations', 'kitchen_name',
            'description', 'description_translations', 'image_url',
            
            # Product type & flags
            'product_type', 'is_combo', 'is_variant', 'is_variant_group',
            'visible', 'channel_overrides',
            
            # Pricing
            'price', 'effective_price', 'overloads', 'bottle_deposit_price',
            
            # Tax rates (read objects, write IDs)
            'delivery_tax_rate', 'delivery_tax_rate_id',
            'takeaway_tax_rate', 'takeaway_tax_rate_id',
            'eat_in_tax_rate', 'eat_in_tax_rate_id',
            
            # Selection rules
            'min_select', 'max_select', 'multi_max', 'max_free',
            'default_quantity', 'sort_order',
            
            # Relationships
            'sub_products',          # READ: SerializerMethodField (list of PLUs)
            'sub_product_plu_list',   # WRITE: ListField (accepts PLU list)
            'pos_category_ids', 'categories',
            'locations', 'current_location_info',
            'auto_apply',
            
            # Nutrition & tags
            'calories', 'calories_range_high', 'nutritional_info',
            'beverage_info', 'packaging', 'supplemental_info', 'product_tags',
            
            # Metadata
            'created_at', 'updated_at', 'is_active',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'plu': {'required': False}  # Auto-generated if not provided
        }
    
    # ========== INPUT FIELD REMAPPING ==========
    
    def to_internal_value(self, data):
        """
        Remap incoming 'sub_products' key to internal 'sub_product_plu_list'.
        
        This allows the API to accept 'sub_products' in the request body
        (backward compatible) while avoiding the name collision with the
        read-only SerializerMethodField of the same name.
        """
        if isinstance(data, dict) and 'sub_products' in data:
            data = data.copy()
            data['sub_product_plu_list'] = data.pop('sub_products')
        return super().to_internal_value(data)
    
    # ========== DYNAMIC FIELD EXCLUSION ==========
    
    def to_representation(self, instance):
        """
        Dynamically handle location fields based on header context.
        
        - WITH X-Location-ID header: Replace 'locations' with current_location_info
        - WITHOUT X-Location-ID header: Replace 'locations' write format with
          full read details, exclude current_location_info
        
        This keeps the response clean by only showing relevant location data.
        """
        data = super().to_representation(instance)
        location = self.context.get('location')
        
        if location:
            # Location header present → remove 'locations' list (use current_location_info)
            data.pop('locations', None)
        else:
            # No location header → replace locations write data with read details,
            # and remove current_location_info
            data.pop('current_location_info', None)
            location_links = instance.location_links.select_related('location').all()
            data['locations'] = LocationAssignmentDetailSerializer(
                location_links,
                many=True
            ).data
        
        return data
    
    # ========== COMPUTED FIELD METHODS ==========
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'string'}})
    def get_sub_products(self, obj):
        """
        Get list of sub-product PLUs in sort order.
        
        Returns PLUs only (not full objects) for efficiency.
        Use NestedProductSerializer for full nested structure.
        
        Args:
            obj (Product): Product instance
            
        Returns:
            list: PLU codes in sort order
            
        Example:
            ["GRP-TOPPIN-A1B2", "GRP-SIZES-C3D4"]
        """
        return list(
            obj.child_relations.order_by('sort_order')
            .values_list('child__plu', flat=True)
        )
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_effective_price(self, obj):
        """
        Calculate effective price with location/channel overrides.
        
        Uses context variables:
        - location: For location-specific pricing
        - channel: For channel-specific pricing
        
        Priority:
        1. Channel price (if location + channel provided)
        2. Location price override (if location provided)
        3. Product base price (fallback)
        
        Args:
            obj (Product): Product instance
            
        Returns:
            int: Price in cents
            
        Note:
            Does NOT include overload pricing (context-dependent).
            Overloads are applied during cart calculation.
        """
        request = self.context.get('request')
        if not request:
            return obj.price
        
        location = self.context.get('location')
        channel = self.context.get('channel')
        
        return obj.get_effective_price(location=location, channel=channel)
    
    
    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_current_location_info(self, obj):
        """
        Get current location assignment details.
        
        Display Logic:
        - Shown ONLY when X-Location-ID header present
        - Hidden when no location header (use locations field instead)
        
        Returns details for specific location including:
        - Location ID and name
        - Availability (base and channel-specific)
        - Pricing (base override and channel-specific)
        - Effective price (calculated)
        - Tax rate overrides
        - Stock quantity
        
        Args:
            obj (Product): Product instance
            
        Returns:
            dict or None: Location info dict, or None if no header
            
        Example Output (assigned):
            {
                "location_id": "uuid",
                "location_name": "NYC Times Square",
                "is_available": true,
                "price_override": 999,
                "channels": {
                    "ubereats": {"price": 1099, "is_available": true}
                },
                "effective_price": 1099,
                "stock_quantity": 50,
                "delivery_tax_rate_override_id": "uuid"
            }
        
        Example Output (not assigned):
            {
                "location_id": "uuid",
                "location_name": "NYC Times Square",
                "is_assigned": false
            }
        """
        location = self.context.get('location')
        
        # Only show if location header present
        if not location:
            return None
        
        try:
            pl = ProductLocation.objects.get(product=obj, location=location)
            channel = self.context.get('channel')
            
            return {
                'location_id': str(location.id),
                'location_name': location.name,
                'is_available': pl.is_available_on_channel(channel) if channel else pl.is_available,
                'price_override': pl.price_override,
                'channels': pl.channels,  # NEW: Consolidated structure
                'stock_quantity': pl.stock_quantity,
                'effective_price': pl.get_price_for_channel(channel) if channel else (pl.price_override or obj.price),
                'delivery_tax_rate_override_id': str(pl.delivery_tax_rate_override_id) if pl.delivery_tax_rate_override_id else None,
                'takeaway_tax_rate_override_id': str(pl.takeaway_tax_rate_override_id) if pl.takeaway_tax_rate_override_id else None,
                'eat_in_tax_rate_override_id': str(pl.eat_in_tax_rate_override_id) if pl.eat_in_tax_rate_override_id else None,
            }
        except ProductLocation.DoesNotExist:
            return {
                'location_id': str(location.id),
                'location_name': location.name,
                'is_assigned': False
            }
    
    # ========== VALIDATION ==========
    
    def validate(self, attrs):
        """
        Validate product data.
        
        Checks:
        1. Selection rules (max >= min for groups)
        2. Price is non-negative
        3. Tax rate IDs exist (if provided)
        
        Args:
            attrs (dict): Validated field data
            
        Returns:
            dict: Validated data
            
        Raises:
            serializers.ValidationError: If validation fails
        """
        product_type = attrs.get('product_type', Product.ProductType.MAIN)
        
        # Validate selection rules for groups
        if product_type == Product.ProductType.MODIFIER_GROUP:
            min_sel = attrs.get('min_select', 0)
            max_sel = attrs.get('max_select', 0)
            
            if min_sel < 0:
                raise serializers.ValidationError({'min_select': 'Must be >= 0'})
            
            if max_sel > 0 and max_sel < min_sel:
                raise serializers.ValidationError({'max_select': 'Must be >= min_select'})
        
        # Validate price
        if 'price' in attrs and attrs['price'] < 0:
            raise serializers.ValidationError({'price': 'Cannot be negative'})
        
        # Validate tax rate IDs
        tax_rate_fields = {
            'delivery_tax_rate_id': 'delivery_tax_rate_id',
            'takeaway_tax_rate_id': 'takeaway_tax_rate_id',
            'eat_in_tax_rate_id': 'eat_in_tax_rate_id',
        }
        errors = {}
        for field_name, attr_key in tax_rate_fields.items():
            tax_rate_id = attrs.get(attr_key)
            if tax_rate_id is not None:
                if not TaxRate.objects.filter(id=tax_rate_id).exists():
                    errors[field_name] = f'Tax rate with ID "{tax_rate_id}" does not exist.'
        if errors:
            raise serializers.ValidationError(errors)
        
        return attrs
    
    # ========== CREATE/UPDATE ==========
    
    @transaction.atomic
    def create(self, validated_data):
        """
        Create product with all relationships.
        
        Process:
        1. Extract relationship data (categories, sub-products, locations)
        2. Extract tax rate IDs
        3. Create Product instance (PLU auto-generated if not provided)
        4. Set tax rates
        5. Set categories
        6. Set sub-products (with circular reference check)
        7. Set location assignments
        8. CASCADE location assignments to sub-products
        
        Args:
            validated_data (dict): Validated data from serializer
            
        Returns:
            Product: Created product instance
            
        Raises:
            serializers.ValidationError: If relationships invalid
            
        Note:
            All operations in transaction - rollback on any error.
        """
        # Extract relationship data
        sub_product_plus = validated_data.pop('sub_product_plu_list', [])
        category_ids = validated_data.pop('pos_category_ids', [])
        location_assignments = validated_data.pop('locations', [])
        
        # CRITICAL: Extract tax rate IDs before creating product
        delivery_tax_rate_id = validated_data.pop('delivery_tax_rate_id', None)
        takeaway_tax_rate_id = validated_data.pop('takeaway_tax_rate_id', None)
        eat_in_tax_rate_id = validated_data.pop('eat_in_tax_rate_id', None)
        
        # Create product (PLU auto-generated in model.save() if not provided)
        product = Product.objects.create(**validated_data)
        
        # Set tax rates
        if delivery_tax_rate_id:
            product.delivery_tax_rate_id = delivery_tax_rate_id
        if takeaway_tax_rate_id:
            product.takeaway_tax_rate_id = takeaway_tax_rate_id
        if eat_in_tax_rate_id:
            product.eat_in_tax_rate_id = eat_in_tax_rate_id
        
        if any([delivery_tax_rate_id, takeaway_tax_rate_id, eat_in_tax_rate_id]):
            product.save()
        
        # Set relationships
        if category_ids:
            self._set_categories(product, category_ids)
        
        if sub_product_plus:
            self._set_sub_products(product, sub_product_plus)
        
        if location_assignments:
            self._set_location_assignments(product, location_assignments)

            # CASCADE TO ALL SUB-PRODUCTS
            self._cascade_location_assignments_to_sub_products(
                product, 
                location_assignments
            )
        
        return product
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Update product with relationships.
        
        Process:
        1. Extract relationship data
        2. Extract tax rate IDs
        3. Update scalar fields
        4. Update tax rates
        5. Update relationships (if provided)
        6. CASCADE location assignments to sub-products (if locations updated)
        
        Note:
            Relationships are only updated if explicitly provided.
            Passing None vs not passing field treated differently:
            - Field not in validated_data: No change
            - Field = None: Clear relationship
            - Field = []: Clear relationship
            - Field = [values]: Replace relationship
        
        Args:
            instance (Product): Product to update
            validated_data (dict): Validated data
            
        Returns:
            Product: Updated product instance
        """
        sub_product_plus = validated_data.pop('sub_product_plu_list', None)
        category_ids = validated_data.pop('pos_category_ids', None)
        location_assignments = validated_data.pop('locations', None)
        
        # Extract tax rate IDs
        delivery_tax_rate_id = validated_data.pop('delivery_tax_rate_id', None)
        takeaway_tax_rate_id = validated_data.pop('takeaway_tax_rate_id', None)
        eat_in_tax_rate_id = validated_data.pop('eat_in_tax_rate_id', None)
        
        # Update scalar fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update tax rates
        if delivery_tax_rate_id is not None:
            instance.delivery_tax_rate_id = delivery_tax_rate_id
        if takeaway_tax_rate_id is not None:
            instance.takeaway_tax_rate_id = takeaway_tax_rate_id
        if eat_in_tax_rate_id is not None:
            instance.eat_in_tax_rate_id = eat_in_tax_rate_id
        
        instance.save()
        
        # Update relationships if provided
        if category_ids is not None:
            self._set_categories(instance, category_ids)
        
        if sub_product_plus is not None:
            self._set_sub_products(instance, sub_product_plus)
        
        if location_assignments is not None:
            self._set_location_assignments(instance, location_assignments)

            # CASCADE TO ALL SUB-PRODUCTS
            self._cascade_location_assignments_to_sub_products(
                instance, 
                location_assignments
            )
        
        return instance

    # ========== CASCADE LOGIC ==========
    
    def _cascade_location_assignments_to_sub_products(
        self, 
        product, 
        location_assignments
    ):
        """
        CASCADE location assignments to ALL nested sub-products recursively.
        
        Process:
        1. Get all immediate sub-products
        2. For each sub-product:
           a. Assign same locations as parent
           b. Recursively cascade to ITS sub-products
        3. Continue until all nested levels processed
        
        Args:
            product (Product): Parent product
            location_assignments (list): Location assignment data from parent
        """
        if not location_assignments:
            return
        
        # Get all immediate sub-products
        sub_products = product.sub_products.all()
        
        if not sub_products.exists():
            return
        
        for sub_product in sub_products:
            # Assign same locations to this sub-product
            self._set_location_assignments(sub_product, location_assignments)
            
            # Recursively cascade to this sub-product's children
            self._cascade_location_assignments_to_sub_products(
                sub_product, 
                location_assignments
            )
    
    # ========== HELPER METHODS ==========
    
    def _set_categories(self, product, category_ids):
        """
        Set product categories from pos_category_id list.
        
        Args:
            product (Product): Product to update
            category_ids (list): List of pos_category_id strings
            
        Raises:
            serializers.ValidationError: If categories not found
        """
        if not category_ids:
            product.categories.clear()
            return
        
        categories = Category.objects.filter(pos_category_id__in=category_ids)
        
        if categories.count() != len(category_ids):
            found_ids = set(categories.values_list('pos_category_id', flat=True))
            missing_ids = set(category_ids) - found_ids
            raise serializers.ValidationError({
                'pos_category_ids': f'Categories not found: {missing_ids}'
            })
        
        product.categories.set(categories)
    
    def _set_sub_products(self, product, sub_product_plus):
        """
        Set sub-products from PLU list.
        
        Process:
        1. Lookup products by PLU
        2. Clear existing relationships
        3. Create new relationships with sort_order
        4. Validate no circular references (DFS)
        
        Args:
            product (Product): Parent product
            sub_product_plus (list): List of child PLU strings
            
        Raises:
            serializers.ValidationError: If PLUs not found or circular reference
        """
        if not sub_product_plus:
            ProductRelation.objects.filter(parent=product).delete()
            return
        
        sub_products = Product.objects.filter(plu__in=sub_product_plus)
        
        if sub_products.count() != len(sub_product_plus):
            found_plus = set(sub_products.values_list('plu', flat=True))
            missing_plus = set(sub_product_plus) - found_plus
            raise serializers.ValidationError({
                'sub_products': f'Products not found: {missing_plus}'
            })
        
        # Clear and recreate
        ProductRelation.objects.filter(parent=product).delete()
        
        plu_to_product = {p.plu: p for p in sub_products}
        relations = [
            ProductRelation(
                parent=product,
                child=plu_to_product[plu],
                sort_order=idx
            )
            for idx, plu in enumerate(sub_product_plus)
        ]
        
        ProductRelation.objects.bulk_create(relations)
        
        # Validate no cycles
        try:
            self._validate_no_cycles(product)
        except DjangoValidationError as e:
            ProductRelation.objects.filter(parent=product).delete()
            raise serializers.ValidationError({'sub_products': str(e)})
    
    def _set_location_assignments(self, product, location_assignments):
        """
        Set location assignments with pricing and tax overrides.
        
        Creates ProductLocation records with:
        - Base pricing and availability
        - Channel-specific pricing (NEW consolidated structure)
        - Tax rate overrides
        - Stock quantities
        
        Args:
            product (Product): Product to assign
            location_assignments (list): List of assignment dicts
            
        Raises:
            serializers.ValidationError: If locations not found
        """
        from locations.models import Location
        
        if not location_assignments:
            ProductLocation.objects.filter(product=product).delete()
            return
        
        # Get all location IDs
        location_ids = [la['location_id'] for la in location_assignments]
        locations = Location.objects.filter(id__in=location_ids)
        
        if locations.count() != len(location_ids):
            found_ids = set(str(loc.id) for loc in locations)
            missing_ids = set(str(lid) for lid in location_ids) - found_ids
            raise serializers.ValidationError({
                'locations': f'Locations not found: {missing_ids}'
            })
        
        # Clear existing
        ProductLocation.objects.filter(product=product).delete()
        
        # Create new assignments
        location_map = {str(loc.id): loc for loc in locations}
        
        for assignment in location_assignments:
            location = location_map[str(assignment['location_id'])]
            
            ProductLocation.objects.create(
                product=product,
                location=location,
                is_available=assignment.get('is_available', True),
                price_override=assignment.get('price_override'),
                channels=assignment.get('channels', {}),  # NEW: Consolidated
                stock_quantity=assignment.get('stock_quantity'),
                delivery_tax_rate_override_id=assignment.get('delivery_tax_rate_override_id'),
                takeaway_tax_rate_override_id=assignment.get('takeaway_tax_rate_override_id'),
                eat_in_tax_rate_override_id=assignment.get('eat_in_tax_rate_override_id'),
            )
    
    def _validate_no_cycles(self, product, visited=None, path=None):
        """
        Validate no circular references using DFS.
        
        Prevents invalid structures like:
        - A → B → A (simple cycle)
        - A → B → C → A (longer cycle)
        - A → A (self-reference)
        
        Args:
            product (Product): Starting product
            visited (set): Visited PLUs
            path (list): Current path
            
        Raises:
            DjangoValidationError: If cycle detected
        """
        if visited is None:
            visited = set()
            path = []
        
        if product.plu in visited:
            raise DjangoValidationError(
                f"Circular reference detected: {' → '.join(path + [product.plu])}"
            )
        
        visited.add(product.plu)
        path.append(product.plu)
        
        for child in product.sub_products.all():
            self._validate_no_cycles(child, visited.copy(), path.copy())



class NestedProductSerializer(serializers.ModelSerializer):
    """
    Recursive serializer for menu export with full nested structure.
    
    Purpose: Generate complete menu tree for delivery platforms.
    Used when: ?expand=sub_products query parameter is provided.
    
    Features:
    - Recursive sub-product expansion (configurable max depth)
    - Context-aware pricing (overloads)
    - Location/channel pricing
    - Location assignment information
    - Tax rate information
    - Compact output (fewer fields than ProductSerializer)
    
    Context Variables:
    - location: For location-specific pricing
    - channel: For channel-specific pricing
    - max_depth: Maximum recursion depth (default: 10)
    - _depth: Current recursion depth (internal)
    - _parent_plu: Parent product PLU (for overload lookup)
    
    Examples:
        >>> # Export menu for NYC UberEats
        >>> serializer = NestedProductSerializer(
        ...     main_products,
        ...     many=True,
        ...     context={
        ...         'location': nyc_location,
        ...         'channel': 'ubereats',
        ...         'max_depth': 10
        ...     }
        ... )
        >>> menu_tree = serializer.data
        
        Output structure:
        [
            {
                "plu": "MAIN-BURGER-A1B2",
                "name": "Cheeseburger",
                "price": 899,
                "effective_price": 899,
                "current_location_info": {...},
                "sub_products": [
                    {
                        "plu": "GRP-TOPPIN-C3D4",
                        "name": "Choose Toppings",
                        "current_location_info": {...},
                        "sub_products": [
                            {
                                "plu": "MOD-LETTUC-E5F6",
                                "name": "Lettuce",
                                "price": 0,
                                "current_location_info": {...}
                            },
                            ...
                        ]
                    },
                    ...
                ]
            },
            ...
        ]
    """
    
    # ========== FIELDS ==========
    
    sub_products = serializers.SerializerMethodField(
        help_text="Recursively nested sub-products"
    )
    
    pos_category_ids = serializers.SerializerMethodField(
        help_text="List of category IDs"
    )
    
    price = serializers.SerializerMethodField(
        help_text="Calculated price with all overrides"
    )
    
    effective_price = serializers.SerializerMethodField(
        help_text="Calculated price with location/channel overrides"
    )
    
    current_location_info = serializers.SerializerMethodField(
        help_text="Current location details (shown when X-Location-ID header present)"
    )
    
    delivery_tax_rate = TaxRateSerializer(
        read_only=True,
        help_text="Delivery tax rate object"
    )
    
    # ========== META ==========
    
    class Meta:
        model = Product
        fields = [
            # Core identifiers
            'id', 'plu', 'pos_product_id',
            
            # Display info
            'name', 'name_translations', 'kitchen_name',
            'description', 'description_translations', 'image_url',
            
            # Product type
            'product_type', 'is_combo', 'is_variant', 'is_variant_group',
            'visible',
            
            # Pricing
            'price', 'effective_price',
            
            # Tax
            'delivery_tax_rate', 'takeaway_tax_rate', 'eat_in_tax_rate',
            
            # Selection rules
            'min_select', 'max_select', 'multi_max', 'max_free',
            'default_quantity', 'sort_order',
            
            # Relationships
            'sub_products', 'pos_category_ids', 'auto_apply',
            
            # Location info
            'current_location_info',
            
            # Nutrition
            'calories', 'calories_range_high', 'nutritional_info', 'product_tags',
            
            # Other
            'gtin',
        ]
    
    # ========== DYNAMIC FIELD HANDLING ==========
    
    def to_representation(self, instance):
        """
        Dynamically handle location fields based on header context.
        
        - WITH X-Location-ID header: Show 'current_location_info'
        - WITHOUT X-Location-ID header: Show 'locations' (all assignments)
        """
        data = super().to_representation(instance)
        location = self.context.get('location')
        
        if location:
            # Location header present → current_location_info shown
            data.pop('locations', None)
        else:
            # No location header → show all locations
            data.pop('current_location_info', None)
            
            # Add locations field
            location_links = instance.location_links.select_related('location').all()
            data['locations'] = LocationAssignmentDetailSerializer(
                location_links,
                many=True
            ).data
        
        return data
    
    # ========== COMPUTED FIELD METHODS ==========
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'string'}})
    def get_pos_category_ids(self, obj):
        """Get list of category IDs"""
        return list(obj.categories.values_list('pos_category_id', flat=True))
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_effective_price(self, obj):
        """
        Calculate effective price with location/channel overrides.
        
        Uses context variables:
        - location: For location-specific pricing
        - channel: For channel-specific pricing
        
        Priority:
        1. Channel price (if location + channel provided)
        2. Location price override (if location provided)
        3. Product base price (fallback)
        """
        location = self.context.get('location')
        channel = self.context.get('channel')
        
        return obj.get_effective_price(location=location, channel=channel)
    
    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_current_location_info(self, obj):
        """
        Get current location assignment details.
        
        Display Logic:
        - Shown ONLY when X-Location-ID header present
        - Hidden when no location header (use locations field instead)
        
        Returns details for specific location including:
        - Location ID and name
        - Availability (base and channel-specific)
        - Pricing (base override and channel-specific)
        - Effective price (calculated)
        - Tax rate overrides
        - Stock quantity
        """
        location = self.context.get('location')
        
        # Only show if location header present
        if not location:
            return None
        
        try:
            pl = ProductLocation.objects.get(product=obj, location=location)
            channel = self.context.get('channel')
            
            return {
                'location_id': str(location.id),
                'location_name': location.name,
                'is_available': pl.is_available_on_channel(channel) if channel else pl.is_available,
                'price_override': pl.price_override,
                'channels': pl.channels,
                'stock_quantity': pl.stock_quantity,
                'effective_price': pl.get_price_for_channel(channel) if channel else (pl.price_override or obj.price),
                'delivery_tax_rate_override_id': str(pl.delivery_tax_rate_override_id) if pl.delivery_tax_rate_override_id else None,
                'takeaway_tax_rate_override_id': str(pl.takeaway_tax_rate_override_id) if pl.takeaway_tax_rate_override_id else None,
                'eat_in_tax_rate_override_id': str(pl.eat_in_tax_rate_override_id) if pl.eat_in_tax_rate_override_id else None,
            }
        except ProductLocation.DoesNotExist:
            return {
                'location_id': str(location.id),
                'location_name': location.name,
                'is_assigned': False
            }
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_sub_products(self, obj):
        """
        Recursively serialize sub-products.

        Tracks recursion depth to prevent infinite loops.
        Stops at max_depth (default: 10).

        Args:
            obj (Product): Product instance

        Returns:
            list: Nested product data
        """
        current_depth = self.context.get('_depth', 0)
        max_depth = self.context.get('max_depth', 10)
        
        if current_depth >= max_depth:
            return []
        
        children = obj.sub_products.through.objects.filter(
            parent=obj
        ).order_by('sort_order').select_related('child')
        
        if not children:
            return []
        
        # Prepare context for child serialization
        child_context = self.context.copy()
        child_context['_depth'] = current_depth + 1
        child_context['_parent_plu'] = obj.plu  # For overload lookup
        
        serializer = NestedProductSerializer(
            [rel.child for rel in children],
            many=True,
            context=child_context
        )
        
        return serializer.data
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_price(self, obj):
        """
        Get effective price with ALL overrides.
        
        Priority:
        1. Context pricing (overloads) - from parent
        2. Channel-specific pricing - from location
        3. Location base pricing - from location
        4. Product base pricing - fallback
        
        Args:
            obj (Product): Product instance
            
        Returns:
            int: Price in cents
        """
        # Check overload first (context-dependent pricing)
        parent_plu = self.context.get('_parent_plu')
        if parent_plu and obj.overloads:
            for overload in obj.overloads:
                if parent_plu in overload.get('scopes', []):
                    overload_price = overload.get('price') or overload.get('bundle_price')
                    if overload_price is not None:
                        return overload_price
        
        # Check location + channel pricing
        location = self.context.get('location')
        channel = self.context.get('channel')
        
        if location:
            try:
                pl = ProductLocation.objects.get(product=obj, location=location)
                return pl.get_price_for_channel(channel)
            except ProductLocation.DoesNotExist:
                pass
        
        return obj.price