from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db import models
from common.models import BaseUUIDModel
from .product import Product



# ==============================================================================
# PRODUCTRELATION MODEL
# ==============================================================================

class ProductRelation(BaseUUIDModel):
    """
    Parent-child relationships for nested product structures.
    
    Defines hierarchical relationships between products:
    - Main products contain modifier groups
    - Modifier groups contain modifier items
    - Combos contain bundle groups
    - Bundle groups contain main products
    
    Business Rules (enforced in clean()):
    - Product cannot be its own child
    - Type-specific nesting rules must be followed
    
    Allowed Relationships:
    - MAIN → [MODIFIER_GROUP, BUNDLE_GROUP]
    - MODIFIER_ITEM → [MODIFIER_GROUP]
    - MODIFIER_GROUP → [MAIN, MODIFIER_ITEM]
    - BUNDLE_GROUP → [MAIN]
    
    Examples:
        >>> # Burger contains Toppings Group
        >>> ProductRelation.objects.create(
        ...     parent=burger,
        ...     child=toppings_group,
        ...     sort_order=0
        ... )
        
        >>> # Toppings Group contains Lettuce
        >>> ProductRelation.objects.create(
        ...     parent=toppings_group,
        ...     child=lettuce,
        ...     sort_order=0
        ... )
    """
    
    # ========== FIELDS ==========
    
    parent = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="child_relations",
        help_text="""
        Parent product (container).
        Examples:
        - Burger (contains toppings group)
        - Toppings Group (contains lettuce, tomato)
        - Combo (contains burger bundle, sides bundle)
        """
    )
    
    child = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="parent_relations",
        help_text="""
        Child product (contained).
        Examples:
        - Toppings Group (contained by burger)
        - Lettuce (contained by toppings group)
        - Burger Bundle (contained by combo)
        """
    )
    
    sort_order = models.IntegerField(
        default=0,
        help_text="""
        Display order among siblings.
        Lower numbers appear first.
        Examples:
            0 = Choose Size (first)
            1 = Choose Toppings (second)
            2 = Choose Extras (third)
        """
    )
    
    auto_apply = models.BooleanField(
        default=False,
        help_text="""
        Whether this child is automatically selected.
        Examples:
        - True: Standard toppings included by default
        - False: Customer must actively select
        """
    )
    
    # ========== META ==========
    
    class Meta:
        unique_together = ("parent", "child")
        ordering = ['sort_order']
        indexes = [
            models.Index(fields=['parent', 'sort_order']),
            models.Index(fields=['child']),
        ]
        verbose_name = "Product Relation"
        verbose_name_plural = "Product Relations"
    
    # ========== METHODS ==========
    
    def __str__(self):
        """String representation: Parent PLU → Child PLU"""
        return f"{self.parent.plu} → {self.child.plu}"
    
    def clean(self):
        """
        Validate relationship constraints.
        
        Rules:
        1. Product cannot be its own child (self-reference)
        2. Type-specific nesting rules must be followed
        
        Raises:
            ValidationError: If any rule is violated
            
        Type-Specific Rules:
        - MAIN can contain: MODIFIER_GROUP, BUNDLE_GROUP
        - MODIFIER_ITEM can contain: MODIFIER_GROUP
        - MODIFIER_GROUP can contain: MAIN, MODIFIER_ITEM
        - BUNDLE_GROUP can contain: MAIN
        """
        super().clean()
        
        # Rule 1: No self-reference
        if self.parent_id == self.child_id:
            raise ValidationError(
                "Product cannot be its own sub-product. "
                "This would create an invalid self-reference."
            )
        
        # Rule 2: Type-specific nesting
        ALLOWED_CHILD_TYPES = {
            Product.ProductType.MAIN: [
                Product.ProductType.MODIFIER_GROUP,
                Product.ProductType.BUNDLE_GROUP
            ],
            Product.ProductType.MODIFIER_ITEM: [
                Product.ProductType.MODIFIER_GROUP
            ],
            Product.ProductType.MODIFIER_GROUP: [
                Product.ProductType.MAIN,
                Product.ProductType.MODIFIER_ITEM
            ],
            Product.ProductType.BUNDLE_GROUP: [
                Product.ProductType.MAIN
            ],
        }
        
        allowed = ALLOWED_CHILD_TYPES.get(self.parent.product_type, [])
        if self.child.product_type not in allowed:
            raise ValidationError(
                f"Invalid nesting: {self.parent.get_product_type_display()} "
                f"cannot contain {self.child.get_product_type_display()}. "
                f"Allowed types: {[Product.ProductType(t).label for t in allowed]}"
            )
