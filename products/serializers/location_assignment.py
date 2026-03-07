from rest_framework import serializers

from ..models import (
    TaxRate,
    ProductLocation
)


# ==============================================================================
# LOCATION ASSIGNMENT SERIALIZERS
# ==============================================================================

class LocationAssignmentDetailSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for displaying location assignments.
    
    Purpose: Show complete location assignment details when listing
    all locations a product is assigned to.
    
    Used in: ProductSerializer.get_locations() when no location header
    
    Fields:
    - location_id: UUID of location
    - location_name: Name of location
    - is_available: Base availability
    - price_override: Base price override
    - channels: Channel-specific data (NEW consolidated structure)
    - stock_quantity: Current stock
    - low_stock_threshold: Alert threshold
    - delivery_tax_rate_override: Tax override for delivery
    - takeaway_tax_rate_override: Tax override for takeaway
    - eat_in_tax_rate_override: Tax override for eat-in
    
    Note: All fields are read-only. For updates, use views.
    
    Examples:
        >>> # Serialize all location assignments
        >>> location_links = product.location_links.all()
        >>> serializer = LocationAssignmentDetailSerializer(
        ...     location_links,
        ...     many=True
        ... )
        >>> print(serializer.data)
        [
            {
                "location_id": "uuid-1",
                "location_name": "NYC Times Square",
                "is_available": true,
                "price_override": 999,
                "channels": {
                    "ubereats": {"price": 1099, "is_available": true}
                }
            }
        ]
    """
    
    # ========== FIELDS ==========
    
    location_id = serializers.UUIDField(
        source='location.id',
        read_only=True,
        help_text="UUID of the location"
    )
    
    location_name = serializers.CharField(
        source='location.name',
        read_only=True,
        help_text="Display name of the location"
    )
    
    # ========== META ==========
    
    class Meta:
        model = ProductLocation
        fields = [
            'location_id',
            'location_name',
            'is_available',
            'price_override',
            'channels',  # NEW: Consolidated channel data
            'stock_quantity',
            'low_stock_threshold',
            'delivery_tax_rate_override',
            'takeaway_tax_rate_override',
            'eat_in_tax_rate_override',
        ]
        read_only_fields = fields


class LocationAssignmentSerializer(serializers.Serializer):
    """
    Write-only serializer for creating/updating location assignments.
    
    Purpose: Handle location assignment data in ProductSerializer
    create/update operations.
    
    Used in: ProductSerializer write operations (POST/PUT/PATCH)
    
    Fields:
    - location_id: UUID of location to assign (required)
    - is_available: Base availability (default: True)
    - price_override: Base price override in cents (optional)
    - channels: Channel-specific data (NEW consolidated structure)
    - stock_quantity: Initial stock quantity (optional)
    - delivery_tax_rate_override_id: Tax override UUID (optional)
    - takeaway_tax_rate_override_id: Tax override UUID (optional)
    - eat_in_tax_rate_override_id: Tax override UUID (optional)
    
    Validation:
    - location_id must exist
    - Tax rate override IDs must exist if provided
    - price_override must be >= 0
    - stock_quantity must be >= 0
    
    Examples:
        >>> # Assign product to NYC with channel pricing
        >>> data = {
        ...     "location_id": "uuid-nyc",
        ...     "is_available": True,
        ...     "price_override": 999,
        ...     "channels": {
        ...         "ubereats": {"price": 1099, "is_available": True},
        ...         "doordash": {"price": 1049, "is_available": False}
        ...     },
        ...     "stock_quantity": 50,
        ...     "delivery_tax_rate_override_id": "uuid-tax"
        ... }
        >>> serializer = LocationAssignmentSerializer(data=data)
        >>> serializer.is_valid()
        >>> # Used internally by ProductSerializer._set_location_assignments()
    """
    
    # ========== FIELDS ==========
    
    location_id = serializers.UUIDField(
        required=True,
        help_text="UUID of location to assign product to"
    )
    
    is_available = serializers.BooleanField(
        default=True,
        help_text="Base availability at this location"
    )
    
    price_override = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        help_text="Base price override in cents (null = use product price)"
    )
    
    channels = serializers.JSONField(
        required=False,
        default=dict,
        help_text="""
        Consolidated channel data structure.
        Format: {
            "channel_name": {
                "price": int (optional),
                "is_available": bool (optional)
            }
        }
        Example: {
            "ubereats": {"price": 1099, "is_available": true},
            "doordash": {"price": 1049, "is_available": false}
        }
        """
    )
    
    stock_quantity = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        help_text="Initial stock quantity at this location"
    )
    
    # Tax rate overrides
    delivery_tax_rate_override_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Override default delivery tax rate for this location"
    )
    
    takeaway_tax_rate_override_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Override default takeaway tax rate for this location"
    )
    
    eat_in_tax_rate_override_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Override default eat-in tax rate for this location"
    )
    
    # ========== METHODS ==========
    
    def validate(self, attrs):
        """
        Validate tax rate override IDs exist.
        
        Checks that any provided tax rate UUIDs reference existing TaxRate records.
        
        Args:
            attrs (dict): Validated field data
            
        Returns:
            dict: Validated data
            
        Raises:
            serializers.ValidationError: If tax rate IDs don't exist
            
        Examples:
            >>> attrs = {"location_id": "...", "delivery_tax_rate_override_id": "invalid"}
            >>> validate(attrs)
            # Raises: ValidationError with message about tax rate not found
        """
        tax_rate_fields = [
            'delivery_tax_rate_override_id',
            'takeaway_tax_rate_override_id',
            'eat_in_tax_rate_override_id',
        ]
        
        errors = {}
        for field_name in tax_rate_fields:
            tax_rate_id = attrs.get(field_name)
            if tax_rate_id is not None:
                if not TaxRate.objects.filter(id=tax_rate_id).exists():
                    errors[field_name] = f'Tax rate with ID "{tax_rate_id}" does not exist.'
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return attrs