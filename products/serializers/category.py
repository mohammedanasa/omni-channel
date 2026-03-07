from rest_framework import serializers
from ..models import Category

# ==============================================================================
# CATEGORY SERIALIZER
# ==============================================================================

class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for Category model.
    
    Handles:
    - CRUD operations for categories
    - Product count computation
    - Multi-language support (name/description translations)
    
    Fields:
    - id: UUID (read-only)
    - pos_category_id: POS system identifier
    - name: Display name
    - name_translations: Translated names (JSONField)
    - description: Optional description
    - description_translations: Translated descriptions (JSONField)
    - image_url: Category image URL
    - sort_order: Display order
    - product_count: Number of products (computed, read-only)
    - created_at, updated_at: Timestamps (read-only)
    
    Examples:
        >>> # Create category
        >>> data = {
        ...     "pos_category_id": "BURGERS",
        ...     "name": "Burgers",
        ...     "name_translations": {"es": "Hamburguesas"},
        ...     "sort_order": 1
        ... }
        >>> serializer = CategorySerializer(data=data)
        >>> serializer.is_valid()
        >>> category = serializer.save()
        
        >>> # Read with product count
        >>> serializer = CategorySerializer(category)
        >>> print(serializer.data['product_count'])  # 15
    """
    
    # ========== COMPUTED FIELDS ==========
    
    product_count = serializers.SerializerMethodField(
        help_text="Number of products assigned to this category"
    )
    
    # ========== META ==========
    
    class Meta:
        model = Category
        fields = [
            'id',
            'pos_category_id',
            'name',
            'name_translations',
            'description',
            'description_translations',
            'image_url',
            'sort_order',
            'product_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    # ========== METHODS ==========
    
    def get_product_count(self, obj):
        """
        Count products in this category.
        
        Args:
            obj (Category): Category instance
            
        Returns:
            int: Number of products
            
        Note:
            Uses prefetch_related in view for performance.
            Without prefetch, this causes N+1 queries.
        """
        return obj.products.count()

