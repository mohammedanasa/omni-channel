from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import BaseUUIDModel



# ==============================================================================
# CATEGORY MODEL
# ==============================================================================

class Category(BaseUUIDModel):
    """
    Product categories for organization and navigation.
    
    Categories are used to:
    1. Organize products in the menu
    2. Filter products by type
    3. Display grouped products in UI
    4. Generate reports by category
    
    Tenant-isolated: Each merchant has their own categories.
    
    Relationships:
    - products: Products assigned to this category (M2M)
    
    Examples:
        >>> # Create category
        >>> burgers = Category.objects.create(
        ...     pos_category_id="BURGERS",
        ...     name="Burgers",
        ...     sort_order=1
        ... )
        
        >>> # Assign products
        >>> product.categories.add(burgers)
        
        >>> # Get all products in category
        >>> burger_products = burgers.products.all()
    """
    
    # ========== FIELDS ==========
    
    pos_category_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="""
        Unique identifier from the POS system.
        Used for external integrations and sync.
        Examples: 'BURGERS', 'DRINKS', 'DESSERTS', 'SIDES'
        Must be unique per tenant.
        """
    )
    
    name = models.CharField(
        max_length=255,
        help_text="""
        Display name of the category.
        Examples: 'Burgers', 'Beverages', 'Desserts', 'Side Dishes'
        """
    )
    
    name_translations = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Translated names for multi-language support.
        Format: {"language_code": "translated_name"}
        Examples:
            {"es": "Hamburguesas", "fr": "Hamburgers"}
            {"es": "Bebidas", "fr": "Boissons"}
        """
    )
    
    description = models.TextField(
        blank=True,
        help_text="""
        Optional description of the category.
        Used for SEO and customer information.
        Examples:
            "Our signature burgers made with 100% Angus beef"
            "Refreshing beverages to complement your meal"
        """
    )
    
    description_translations = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Translated descriptions for multi-language support.
        Format: {"language_code": "translated_description"}
        """
    )
    
    image_url = models.URLField(
        blank=True,
        max_length=500,
        help_text="""
        URL to category image/icon.
        Examples:
            "https://cdn.example.com/categories/burgers.jpg"
            "https://images.example.com/drinks-icon.png"
        """
    )
    
    sort_order = models.IntegerField(
        default=0,
        help_text="""
        Display order in menus and lists.
        Lower numbers appear first.
        Examples:
            0 = Featured
            1 = Burgers
            2 = Sides
            3 = Drinks
        """
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when category was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when category was last modified"
    )
    
    # ========== META ==========
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['pos_category_id']),
            models.Index(fields=['sort_order']),
        ]
    
    # ========== METHODS ==========
    
    def __str__(self):
        """
        String representation.
        
        Returns:
            str: POS ID and name
            
        Example:
            "BURGERS - Burgers"
        """
        return f"{self.pos_category_id} - {self.name}"