from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ..models import TaxRate


# ==============================================================================
# TAX RATE SERIALIZER
# ==============================================================================

class TaxRateSerializer(serializers.ModelSerializer):
    """
    Serializer for TaxRate model with validation.
    
    Handles:
    - CRUD operations for tax rates
    - Validation: percentage XOR flat_fee (mutually exclusive)
    - Display value calculation (human-readable format)
    - Auto-switch default behavior (handled in model)
    
    Fields:
    - id: UUID (read-only)
    - name: Tax rate name
    - percentage: Percentage value (3 decimal precision)
    - flat_fee: Flat fee in cents
    - display_value: Human-readable value (computed)
    - is_default: Default flag
    - description: Optional description
    - is_active: Active status
    - created_at, updated_at: Timestamps (read-only)
    
    Validation Rules:
    1. Must have EITHER percentage OR flat_fee (not both, not neither)
    2. Percentage: 0 to 100000 (0% to 100%)
    3. Flat fee: >= 0
    
    Examples:
        >>> # Create percentage tax
        >>> data = {
        ...     "name": "VAT 20%",
        ...     "percentage": 20000,
        ...     "is_default": True
        ... }
        >>> serializer = TaxRateSerializer(data=data)
        >>> serializer.is_valid()  # True
        >>> tax_rate = serializer.save()
        
        >>> # Invalid: both percentage and flat_fee
        >>> data = {
        ...     "name": "Invalid",
        ...     "percentage": 9000,
        ...     "flat_fee": 10
        ... }
        >>> serializer = TaxRateSerializer(data=data)
        >>> serializer.is_valid()  # False
        >>> print(serializer.errors)
        # {"non_field_errors": ["Tax rate cannot have both..."]}
    """
    
    # ========== COMPUTED FIELDS ==========
    
    display_value = serializers.SerializerMethodField(
        help_text="""
        Human-readable display of tax value.
        Examples:
            "9.000%" for percentage
            "$0.10" for flat fee
            "N/A" if neither (should not happen)
        """
    )
    
    # ========== META ==========
    
    class Meta:
        model = TaxRate
        fields = [
            'id',
            'name',
            'percentage',
            'flat_fee',
            'display_value',
            'is_default',
            'description',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    # ========== METHODS ==========
    
    @extend_schema_field(OpenApiTypes.STR)
    def get_display_value(self, obj):
        """
        Generate human-readable tax value.
        
        Converts internal representation to display format:
        - Percentage: percentage / 1000 with 3 decimals + "%"
        - Flat fee: flat_fee / 100 with 2 decimals + "$"
        
        Args:
            obj (TaxRate): TaxRate instance
            
        Returns:
            str: Formatted display value
            
        Examples:
            >>> tax = TaxRate(percentage=9000)
            >>> get_display_value(tax)
            "9.000%"
            
            >>> tax = TaxRate(flat_fee=10)
            >>> get_display_value(tax)
            "$0.10"
        """
        if obj.percentage is not None:
            return f"{obj.percentage / 1000:.3f}%"
        elif obj.flat_fee is not None:
            return f"${obj.flat_fee / 100:.2f}"
        return "N/A"
    
    def validate(self, attrs):
        """
        Validate percentage XOR flat_fee constraint.
        
        Business Rule: Tax rate must have EITHER percentage OR flat_fee,
        but not both and not neither.
        
        Args:
            attrs (dict): Validated field data
            
        Returns:
            dict: Validated data (unchanged if valid)
            
        Raises:
            serializers.ValidationError: If constraint violated
            
        Examples:
            >>> # Valid: Only percentage
            >>> attrs = {"name": "Tax", "percentage": 9000}
            >>> validate(attrs)  # Returns attrs unchanged
            
            >>> # Invalid: Both set
            >>> attrs = {"name": "Tax", "percentage": 9000, "flat_fee": 10}
            >>> validate(attrs)  # Raises ValidationError
            
            >>> # Invalid: Neither set
            >>> attrs = {"name": "Tax"}
            >>> validate(attrs)  # Raises ValidationError
        """
        has_percentage = attrs.get('percentage') is not None
        has_flat_fee = attrs.get('flat_fee') is not None
        
        if has_percentage and has_flat_fee:
            raise serializers.ValidationError(
                "Tax rate cannot have both percentage and flat_fee. Choose one."
            )
        
        if not has_percentage and not has_flat_fee:
            raise serializers.ValidationError(
                "Tax rate must have either percentage or flat_fee."
            )
        
        return attrs

