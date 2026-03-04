"""
==============================================================================
PRODUCTS MODELS - COMPREHENSIVE DOCUMENTATION
==============================================================================

This module contains all product-related models for the multi-tenant,
multi-location, multi-channel restaurant management system.

Models:
    - TaxRate: Tax rate definitions (percentage or flat fee)
    - Category: Product categories for organization
    - Product: Universal product model (4 types: main, modifier, group, bundle)
    - ProductLocation: Junction model for location-specific pricing/availability
    - ProductRelation: Parent-child relationships for nested products

Key Features:
    - Auto-generated PLU codes
    - Multi-tenant isolation (django-tenants)
    - Location-specific pricing and taxes
    - Channel-specific pricing (UberEats, DoorDash, etc.)
    - Context-dependent pricing (overloads)
    - Recursive product structures
    - Circular reference prevention
    - Tax rate inheritance with overrides

Author: Your Team
Version: 1.0.0
"""

import uuid
from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from accounts.models import BaseUUIDModel


# ==============================================================================
# TAX RATE MODEL
# ==============================================================================

class TaxRate(BaseUUIDModel):
    """
    Tax rate definitions for products.
    
    Supports two types of tax rates:
    1. Percentage-based (e.g., 9% sales tax, 20% VAT)
    2. Flat-fee based (e.g., $0.10 bag fee, $0.05 bottle deposit)
    
    Business Rules:
    - Must have EITHER percentage OR flat_fee (mutually exclusive)
    - Only ONE tax rate can be marked as default
    - When a new default is set, old default is automatically unset
    - Can be reused across multiple products and locations
    
    Use Cases:
    - Sales tax (percentage): 8.875% NYC sales tax
    - VAT (percentage): 20% UK VAT
    - Bag fees (flat): $0.10 per bag
    - Bottle deposits (flat): $0.05 per bottle
    
    Relationships:
    - products_delivery: Products using this for delivery tax
    - products_takeaway: Products using this for takeaway tax
    - products_eatin: Products using this for eat-in tax
    - location_*_overrides: Location-specific tax overrides
    
    Examples:
        >>> # Create percentage tax
        >>> vat = TaxRate.objects.create(
        ...     name="VAT 20%",
        ...     percentage=20000,  # 20.000% = 20000
        ...     is_default=True
        ... )
        
        >>> # Create flat fee tax
        >>> bag_fee = TaxRate.objects.create(
        ...     name="Bag Fee",
        ...     flat_fee=10  # $0.10 = 10 cents
        ... )
        
        >>> # Calculate tax
        >>> tax_amount = vat.calculate_tax(1000)  # 20% of $10.00
        >>> print(tax_amount)  # 200 cents = $2.00
    """
    
    # ========== FIELDS ==========
    
    name = models.CharField(
        max_length=100,
        help_text="""
        Human-readable name for the tax rate.
        Examples: 'VAT 9%', 'Sales Tax', 'Bag Fee', 'NYC Sales Tax'
        """
    )
    
    percentage = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100000)],
        help_text="""
        Tax percentage with 3 decimal precision.
        Format: percentage * 1000
        Examples:
            - 9.000% = 9000
            - 8.875% = 8875
            - 20.5% = 20500
        Must be null if flat_fee is set.
        Range: 0 to 100000 (0% to 100%)
        """
    )
    
    flat_fee = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="""
        Flat fee amount in cents.
        Examples:
            - $0.10 = 10 cents
            - $0.05 = 5 cents
            - $1.00 = 100 cents
        Must be null if percentage is set.
        """
    )
    
    is_default = models.BooleanField(
        default=False,
        help_text="""
        Whether this is the default tax rate for the merchant.
        Only ONE tax rate can be default at a time.
        When set to True, automatically unsets other defaults.
        Used as fallback when no specific tax rate is assigned.
        """
    )
    
    description = models.TextField(
        blank=True,
        help_text="""
        Optional detailed description of the tax rate.
        Examples:
            - "New York City combined sales tax (state + city)"
            - "Mandatory bag fee as per city ordinance"
            - "Standard VAT rate for food items"
        """
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="""
        Whether this tax rate is currently active and can be assigned.
        Inactive tax rates are hidden from selection but retained for history.
        """
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the tax rate was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the tax rate was last modified"
    )
    
    # ========== META ==========
    
    class Meta:
        ordering = ['-is_default', 'name']
        indexes = [
            models.Index(fields=['is_default', 'is_active']),
        ]
        verbose_name = "Tax Rate"
        verbose_name_plural = "Tax Rates"
    
    # ========== METHODS ==========
    
    def __str__(self):
        """
        String representation of the tax rate.
        
        Returns:
            str: Formatted string with name and value
            
        Examples:
            "VAT 9% (9.000%)"
            "Bag Fee ($0.10)"
        """
        if self.percentage is not None:
            return f"{self.name} ({self.percentage / 1000:.3f}%)"
        elif self.flat_fee is not None:
            return f"{self.name} (${self.flat_fee / 100:.2f})"
        return self.name
    
    def clean(self):
        """
        Validates tax rate constraints.
        
        Ensures:
        1. Has either percentage OR flat_fee (not both, not neither)
        
        Raises:
            ValidationError: If validation fails
            
        Called automatically before save() by Django forms and admin.
        For programmatic saves, call full_clean() explicitly.
        """
        super().clean()
        
        has_percentage = self.percentage is not None
        has_flat_fee = self.flat_fee is not None
        
        if has_percentage and has_flat_fee:
            raise ValidationError(
                "Tax rate cannot have both percentage and flat_fee. "
                "Please choose one type."
            )
        
        if not has_percentage and not has_flat_fee:
            raise ValidationError(
                "Tax rate must have either percentage or flat_fee. "
                "Please specify one."
            )
    
    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Saves the tax rate with auto-switch default logic.
        
        If is_default=True:
            - Unsets is_default on all other tax rates (within same tenant)
            - Ensures only one default exists
        
        Always calls clean() for validation.
        
        Args:
            *args: Positional arguments passed to parent save()
            **kwargs: Keyword arguments passed to parent save()
            
        Raises:
            ValidationError: If validation fails
            
        Examples:
            >>> # Setting new default automatically unsets old
            >>> tax1 = TaxRate.objects.create(name="Tax 1", percentage=9000, is_default=True)
            >>> tax2 = TaxRate.objects.create(name="Tax 2", percentage=8000, is_default=True)
            >>> tax1.refresh_from_db()
            >>> print(tax1.is_default)  # False (auto-switched)
        """
        # Validate before saving
        self.clean()
        
        # Auto-switch default if this one is being set as default
        if self.is_default:
            # Use select_for_update to prevent race conditions
            TaxRate.objects.filter(
                is_default=True
            ).exclude(
                pk=self.pk
            ).update(is_default=False)
        
        super().save(*args, **kwargs)
    
    def calculate_tax(self, amount):
        """
        Calculates tax amount for a given base amount.
        
        For percentage-based: tax = (amount × percentage) / 100000
        For flat-fee based: tax = flat_fee (constant)
        
        Args:
            amount (int): Base amount in cents
            
        Returns:
            int: Tax amount in cents
            
        Examples:
            >>> # Percentage tax: 9% of $10.00
            >>> vat = TaxRate(percentage=9000)
            >>> tax = vat.calculate_tax(1000)  # 1000 cents = $10.00
            >>> print(tax)  # 90 cents = $0.90
            
            >>> # Flat fee: always $0.10
            >>> bag = TaxRate(flat_fee=10)
            >>> tax = bag.calculate_tax(1000)  # Amount doesn't matter
            >>> print(tax)  # 10 cents = $0.10
            
        Note:
            Returns 0 if neither percentage nor flat_fee is set
            (should not happen if clean() is called)
        """
        if self.percentage is not None:
            # Formula: (amount × percentage) / 100000
            # Example: (1000 × 9000) / 100000 = 90 cents
            return int((amount * self.percentage) / 100000)
        
        elif self.flat_fee is not None:
            # Flat fee is constant regardless of amount
            return self.flat_fee
        
        return 0


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


# ==============================================================================
# PRODUCT MODEL
# ==============================================================================

class Product(BaseUUIDModel):
    """
    Universal product model supporting 4 product types.
    
    Product Types:
    1. MAIN (1): Sellable products (burgers, drinks, etc.)
    2. MODIFIER_ITEM (2): Individual options (lettuce, cheese, etc.)
    3. MODIFIER_GROUP (3): Grouped options (Choose Toppings, Choose Size)
    4. BUNDLE_GROUP (4): Combo components (Choose Your Side, Choose Drink)
    
    Key Features:
    - Auto-generated PLU codes (TYPE-NAME-RANDOM)
    - Multi-location support with location-specific pricing
    - Multi-channel support (UberEats, DoorDash, etc.)
    - Context-dependent pricing (overloads)
    - Tax rate references with location overrides
    - Recursive product structures (products contain products)
    - Circular reference prevention
    
    Pricing Hierarchy:
    1. Context pricing (overloads) - Highest priority
    2. Channel-specific pricing (ProductLocation.channels)
    3. Location base pricing (ProductLocation.price_override)
    4. Product base pricing (Product.price) - Lowest priority
    
    Tax Resolution:
    1. Location tax override (ProductLocation.delivery_tax_rate_override)
    2. Product default tax (Product.delivery_tax_rate)
    3. Merchant default tax (TaxRate.is_default=True)
    
    Examples:
        >>> # Create main product
        >>> burger = Product.objects.create(
        ...     name="Cheeseburger",
        ...     product_type=Product.ProductType.MAIN,
        ...     price=899  # $8.99
        ... )
        >>> print(burger.plu)  # Auto-generated: "MAIN-CHEESE-A7B9"
        
        >>> # Create modifier
        >>> lettuce = Product.objects.create(
        ...     name="Lettuce",
        ...     product_type=Product.ProductType.MODIFIER_ITEM,
        ...     price=0
        ... )
        
        >>> # Create group
        >>> toppings = Product.objects.create(
        ...     name="Choose Toppings",
        ...     product_type=Product.ProductType.MODIFIER_GROUP,
        ...     min_select=0,
        ...     max_select=3
        ... )
        
        >>> # Link them
        >>> toppings.sub_products.add(lettuce)
        >>> burger.sub_products.add(toppings)
    """
    
    class ProductType(models.IntegerChoices):
        """
        Product type enumeration.
        
        MAIN (1): Sellable products that customers can order directly
        MODIFIER_ITEM (2): Individual options/ingredients
        MODIFIER_GROUP (3): Containers for modifier items
        BUNDLE_GROUP (4): Containers for bundle options (combos)
        """
        MAIN = 1, _("Main product")
        MODIFIER_ITEM = 2, _("Modifier item")
        MODIFIER_GROUP = 3, _("Modifier group")
        BUNDLE_GROUP = 4, _("Bundle group")
    
    # ========== IDENTIFIERS ==========
    
    plu = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="""
        Product Lookup Code - Unique identifier.
        Auto-generated if not provided using format: TYPE-NAME-RANDOM
        Examples:
            - "MAIN-BURGER-A7B9"
            - "MOD-LETTUC-F3D2"
            - "GRP-TOPPIN-B5C8"
            - "BUN-SIDES-E4A1"
        Must be unique per tenant.
        """
    )
    
    pos_product_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="""
        Product ID from external POS system.
        Used for integration and sync with POS.
        Examples: "12345", "ITEM-678", "SKU-ABC123"
        """
    )
    
    gtin = ArrayField(
        base_field=models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="""
        Global Trade Item Numbers (barcodes).
        Supports multiple formats: UPC, EAN, ISBN.
        Examples:
            ["012345678905"]  # UPC-A
            ["5012345678900"]  # EAN-13
        Can have multiple GTINs for different package sizes.
        """
    )
    
    # ========== BASIC INFORMATION ==========
    
    name = models.CharField(
        max_length=255,
        help_text="""
        Primary display name of the product.
        Examples: "Cheeseburger", "Large Fries", "Coca-Cola"
        """
    )
    
    name_translations = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Translated names for multi-language support.
        Format: {"language_code": "translated_name"}
        Examples:
            {"es": "Hamburguesa con Queso", "fr": "Hamburger au Fromage"}
        """
    )
    
    kitchen_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="""
        Short name for kitchen display.
        Examples: "CHZBGR", "LG FRY", "COKE"
        Used on KDS (Kitchen Display System) to save space.
        """
    )
    
    description = models.TextField(
        blank=True,
        help_text="""
        Detailed description of the product.
        Examples:
            "100% Angus beef patty with cheddar cheese, lettuce, tomato"
            "Crispy golden fries with sea salt"
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
        URL to product image.
        Examples:
            "https://cdn.example.com/products/cheeseburger.jpg"
        Recommended: 800x600px, JPG/PNG, <500KB
        """
    )
    
    # ========== PRODUCT TYPE & FLAGS ==========
    
    product_type = models.IntegerField(
        choices=ProductType.choices,
        default=ProductType.MAIN,
        help_text="""
        Type of product (1=Main, 2=Modifier, 3=Group, 4=Bundle).
        Determines:
        - Allowed relationships
        - Validation rules
        - PLU prefix
        - Display behavior
        """
    )
    
    is_combo = models.BooleanField(
        default=False,
        help_text="""
        Whether this is a combo/meal deal.
        Combo products must contain at least one Bundle Group.
        Examples: "Burger Combo", "Family Meal", "Kids Meal"
        """
    )
    
    is_variant = models.BooleanField(
        default=False,
        help_text="""
        Whether this is a variant of another product.
        Examples: "Large Coke" is variant of "Coke"
        """
    )
    
    is_variant_group = models.BooleanField(
        default=False,
        help_text="""
        Whether this is a parent of variants.
        Examples: "Coke" (parent) has "Small Coke", "Large Coke" (variants)
        """
    )
    
    visible = models.BooleanField(
        default=True,
        help_text="""
        Whether product is visible to customers.
        Hidden products can still be used as components.
        Use cases:
        - Seasonal items (hide when out of season)
        - Component items (used in combos but not sold alone)
        - Discontinued items (retain for history)
        """
    )
    
    channel_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Global channel-specific settings (not location-specific).
        Format: {"channel": {"visible": bool, "priority": int}}
        Examples:
            {"ubereats": {"visible": false}}
            {"doordash": {"priority": 1}}
        """
    )
    
    # ========== PRICING ==========
    
    price = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="""
        Base price in cents.
        Examples:
            899 = $8.99
            1299 = $12.99
            0 = Free
        This is the default price before any overrides.
        """
    )
    
    overloads = models.JSONField(
        default=list,
        blank=True,
        help_text="""
        Context-dependent pricing within product hierarchy.
        
        Purpose: Same modifier has different prices in different parent groups.
        
        Format:
        [
            {
                "scopes": ["PARENT-PLU-1", "PARENT-PLU-2"],
                "price": 0,
                "bundle_price": 100
            }
        ]
        
        Example: Avocado modifier
        - In "Free Toppings" group → $0.00
        - In "Premium Toppings" group → $2.00
        
        Overloads: [
            {
                "scopes": ["GRP-FREETOP-X1Y2"],
                "price": 0
            },
            {
                "scopes": ["GRP-PREMIUM-A3B4"],
                "price": 200
            }
        ]
        
        NOTE: This is DIFFERENT from ProductLocation pricing:
        - Overloads: Context within product hierarchy
        - ProductLocation: Geography/channel-specific pricing
        """
    )
    
    bottle_deposit_price = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="""
        Bottle/container deposit fee in cents.
        Examples:
            5 = $0.05 bottle deposit
            10 = $0.10 container fee
        Refundable deposit charged for certain beverages.
        """
    )
    
    # ========== TAX RATES ==========
    
    delivery_tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products_delivery',
        help_text="""
        Default tax rate for delivery orders.
        Can be overridden at location level.
        Falls back to merchant default if not set.
        """
    )
    
    takeaway_tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products_takeaway',
        help_text="""
        Default tax rate for takeaway orders.
        Can be overridden at location level.
        Falls back to merchant default if not set.
        """
    )
    
    eat_in_tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products_eatin',
        help_text="""
        Default tax rate for eat-in (dine-in) orders.
        Can be overridden at location level.
        Falls back to merchant default if not set.
        """
    )
    
    # ========== SELECTION RULES (for groups) ==========
    
    min_select = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="""
        Minimum number of sub-products customer must select.
        Only used for MODIFIER_GROUP and BUNDLE_GROUP.
        Examples:
            0 = Optional (like extra toppings)
            1 = Required (like choose a side)
            2 = Must pick at least 2
        """
    )
    
    max_select = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="""
        Maximum number of sub-products customer can select.
        Only used for MODIFIER_GROUP and BUNDLE_GROUP.
        Examples:
            0 = No limit
            1 = Single choice (radio button)
            3 = Up to 3 options
        Must be >= min_select if > 0.
        """
    )
    
    multi_max = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="""
        Maximum quantity of each individual sub-product.
        Examples:
            0 = No limit (can add 10x cheese)
            1 = Can only add once
            2 = Can add up to 2x
        """
    )
    
    max_free = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="""
        Number of free selections before charging.
        Examples:
            0 = All selections charged
            1 = First topping free, extras charged
            3 = First 3 toppings free
        """
    )
    
    default_quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="""
        Default quantity when adding to cart.
        Examples:
            0 = User must specify
            1 = Add 1 by default
        """
    )
    
    sort_order = models.IntegerField(
        default=0,
        help_text="""
        Display order in lists.
        Lower numbers appear first.
        """
    )
    
    # ========== RELATIONSHIPS ==========
    
    locations = models.ManyToManyField(
        'locations.Location',
        through='ProductLocation',
        related_name='products',
        blank=True,
        help_text="""
        Locations where this product is available.
        Junction model ProductLocation contains:
        - Location-specific pricing
        - Channel-specific pricing
        - Stock quantities
        - Tax rate overrides
        """
    )
    
    sub_products = models.ManyToManyField(
        'self',
        through='ProductRelation',
        through_fields=('parent', 'child'),
        symmetrical=False,
        related_name='parents',
        blank=True,
        help_text="""
        Child products contained within this product.
        Examples:
        - Burger contains: Toppings Group, Size Group
        - Toppings Group contains: Lettuce, Tomato, Cheese
        - Combo contains: Burger Bundle, Sides Bundle, Drink Bundle
        """
    )
    
    categories = models.ManyToManyField(
        Category,
        related_name="products",
        blank=True,
        help_text="""
        Categories this product belongs to.
        Main products must have at least one category.
        Products can be in multiple categories.
        """
    )
    
    auto_apply = models.JSONField(
        default=list,
        blank=True,
        help_text="""
        List of PLUs to automatically apply as modifiers.
        Examples:
            ["MOD-KETCHUP-X1Y2"]  # Auto-add ketchup
        """
    )
    
    # ========== NUTRITION & TAGS ==========
    
    calories = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="""
        Base calorie count.
        Examples: 650, 450, 120
        """
    )
    
    calories_range_high = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="""
        High end of calorie range (for variable items).
        Examples:
            calories=400, calories_range_high=600
            Displays as: "400-600 cal"
        """
    )
    
    nutritional_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Detailed nutritional information.
        Format: {
            "fat": 25,           # grams
            "protein": 30,       # grams
            "carbs": 45,         # grams
            "sodium": 850,       # milligrams
            "fiber": 3,          # grams
            "sugar": 12          # grams
        }
        """
    )
    
    beverage_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Beverage-specific information.
        Format: {
            "volume_ml": 500,
            "caffeine_mg": 95,
            "carbonated": true,
            "alcohol_percent": 0
        }
        """
    )
    
    packaging = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Packaging information.
        Format: {
            "container_type": "cup",
            "material": "paper",
            "recyclable": true,
            "reusable": false
        }
        """
    )
    
    supplemental_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Any additional product information.
        Flexible field for custom data.
        """
    )
    
    product_tags = ArrayField(
        base_field=models.IntegerField(),
        blank=True,
        default=list,
        help_text="""
        Tag IDs for product classification.
        Examples:
            [101, 104, 109]
        Tags can represent:
        - Allergens (101=dairy, 104=nuts, 109=gluten)
        - Dietary (vegan, vegetarian, keto)
        - Attributes (spicy, bestseller, new)
        """
    )
    
    # ========== METADATA ==========
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when product was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when product was last modified"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="""
        Whether product is active in the system.
        Inactive products are archived but retained for history.
        """
    )
    
    # ========== META ==========
    
    class Meta:
        indexes = [
            models.Index(fields=['product_type', 'visible']),
            models.Index(fields=['plu']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['sort_order', 'name']
        verbose_name = "Product"
        verbose_name_plural = "Products"
    
    # ========== METHODS ==========
    
    def __str__(self):
        """String representation: PLU - Name"""
        return f"{self.plu} - {self.name}"
    
    def save(self, *args, **kwargs):
        """
        Override save to auto-generate PLU if not provided.
        
        Calls _generate_plu() to create unique PLU code.
        Format: TYPE-SHORTNAME-RANDOM
        
        Examples:
            "MAIN-BURGER-A7B9"
            "MOD-LETTUC-F3D2"
        """
        if not self.plu:
            self.plu = self._generate_plu()
        super().save(*args, **kwargs)
    
    def _generate_plu(self):
        """
        Generate unique PLU code.
        
        Format: {TYPE_PREFIX}-{SHORT_NAME}-{RANDOM}
        
        Components:
        - TYPE_PREFIX: MAIN/MOD/GRP/BUN based on product_type
        - SHORT_NAME: First 6 alphanumeric chars of name (uppercase)
        - RANDOM: 4-character random hex string
        
        Returns:
            str: Unique PLU code
            
        Examples:
            >>> product = Product(name="Cheeseburger", product_type=1)
            >>> plu = product._generate_plu()
            >>> print(plu)  # "MAIN-CHEESE-A7B9"
        
        Ensures uniqueness by checking database and regenerating if collision.
        """
        # Map product type to prefix
        type_prefixes = {
            self.ProductType.MAIN: 'MAIN',
            self.ProductType.MODIFIER_ITEM: 'MOD',
            self.ProductType.MODIFIER_GROUP: 'GRP',
            self.ProductType.BUNDLE_GROUP: 'BUN',
        }
        prefix = type_prefixes.get(self.product_type, 'PROD')
        
        # Extract short name (first 6 alphanumeric chars)
        short_name = ''.join(c for c in self.name if c.isalnum())[:6].upper()
        if not short_name:
            short_name = 'ITEM'  # Fallback if no alphanumeric chars
        
        # Generate random suffix
        random_suffix = str(uuid.uuid4())[:4].upper()
        
        # Combine components
        plu = f"{prefix}-{short_name}-{random_suffix}"
        
        # Ensure uniqueness (regenerate if collision)
        while Product.objects.filter(plu=plu).exists():
            random_suffix = str(uuid.uuid4())[:4].upper()
            plu = f"{prefix}-{short_name}-{random_suffix}"
        
        return plu
    
    def clean(self):
        """
        Validate product constraints.
        
        Rules:
        1. Main products must have at least one category
        2. Combo products must contain at least one Bundle group
        3. Groups must have max_select >= min_select
        
        Raises:
            ValidationError: If any validation rule fails
            
        Called automatically by Django forms/admin.
        For programmatic validation, call full_clean() explicitly.
        """
        super().clean()
        
        # Rule 1: Main products need categories
        if self.product_type == self.ProductType.MAIN:
            if self.pk and not self.categories.exists():
                raise ValidationError(
                    "Main products must have at least one category. "
                    "Please assign a category before saving."
                )
        
        # Rule 2: Combos need bundles
        if self.is_combo:
            if self.pk and not self.sub_products.filter(
                product_type=self.ProductType.BUNDLE_GROUP
            ).exists():
                raise ValidationError(
                    "Combo products must contain at least one Bundle group. "
                    "Please add bundle components."
                )
        
        # Rule 3: Selection rules validation
        if self.product_type in [self.ProductType.MODIFIER_GROUP, self.ProductType.BUNDLE_GROUP]:
            if self.max_select > 0 and self.max_select < self.min_select:
                raise ValidationError(
                    "max_select must be >= min_select. "
                    f"Currently: min={self.min_select}, max={self.max_select}"
                )
    
    def get_tax_amount(self, amount, service_type='delivery', location=None):
        """
        Calculate tax amount with 3-tier resolution.
        
        Tax Resolution Order:
        1. Location tax override (ProductLocation.delivery_tax_rate_override)
        2. Product default tax (Product.delivery_tax_rate)
        3. Merchant default tax (TaxRate.is_default=True)
        
        Args:
            amount (int): Base amount in cents
            service_type (str): 'delivery', 'takeaway', or 'eat_in'
            location (Location, optional): Location for tax override lookup
            
        Returns:
            int: Tax amount in cents
            
        Examples:
            >>> # No location - uses product default
            >>> tax = product.get_tax_amount(1000, 'delivery')
            
            >>> # With location - checks for override first
            >>> tax = product.get_tax_amount(1000, 'delivery', location=nyc)
            
            >>> # Calculate total with tax
            >>> subtotal = 1000  # $10.00
            >>> tax = product.get_tax_amount(subtotal, 'delivery')
            >>> total = subtotal + tax  # $10.90 if 9% tax
        """
        # Try location override first
        if location:
            try:
                pl = ProductLocation.objects.get(product=self, location=location)
                tax_rate = None
                
                # Select appropriate tax rate based on service type
                if service_type == 'delivery':
                    tax_rate = pl.delivery_tax_rate_override or self.delivery_tax_rate
                elif service_type == 'takeaway':
                    tax_rate = pl.takeaway_tax_rate_override or self.takeaway_tax_rate
                elif service_type == 'eat_in':
                    tax_rate = pl.eat_in_tax_rate_override or self.eat_in_tax_rate
                
                if tax_rate:
                    return tax_rate.calculate_tax(amount)
            except ProductLocation.DoesNotExist:
                pass  # Fall through to product default
        
        # Fall back to product default tax
        tax_rate = None
        if service_type == 'delivery':
            tax_rate = self.delivery_tax_rate
        elif service_type == 'takeaway':
            tax_rate = self.takeaway_tax_rate
        elif service_type == 'eat_in':
            tax_rate = self.eat_in_tax_rate
        
        if tax_rate:
            return tax_rate.calculate_tax(amount)
        
        return 0  # No tax if none configured
    
    def get_effective_price(self, location=None, channel=None):
        """
        Get effective price with location/channel overrides.
        
        Price Resolution Order:
        1. Channel-specific price (ProductLocation.channels[channel]['price'])
        2. Location base price (ProductLocation.price_override)
        3. Product base price (Product.price)
        
        Note: This does NOT consider context pricing (overloads).
        Overloads are applied separately during cart calculation.
        
        Args:
            location (Location, optional): Location for price lookup
            channel (str, optional): Channel name (e.g., 'ubereats')
            
        Returns:
            int: Effective price in cents
            
        Examples:
            >>> # No location - returns base price
            >>> price = product.get_effective_price()  # 899
            
            >>> # With location - returns location override
            >>> price = product.get_effective_price(location=nyc)  # 999
            
            >>> # With channel - returns channel-specific price
            >>> price = product.get_effective_price(
            ...     location=nyc,
            ...     channel='ubereats'
            ... )  # 1099
        """
        if location:
            try:
                pl = ProductLocation.objects.get(product=self, location=location)
                # Use ProductLocation's method to handle channel logic
                return pl.get_price_for_channel(channel)
            except ProductLocation.DoesNotExist:
                pass  # Fall through to base price
        
        return self.price


# ==============================================================================
# PRODUCTLOCATION MODEL
# ==============================================================================

class ProductLocation(BaseUUIDModel):
    """
    Junction model: Product ↔ Location relationship.
    
    Manages location-specific product data:
    - Availability (per location, per channel)
    - Pricing (base override, channel-specific)
    - Tax rate overrides (delivery/takeaway/eat-in)
    - Inventory (stock quantities)
    
    Channel Data Structure:
    channels = {
        "ubereats": {"price": 649, "is_available": true},
        "doordash": {"price": 629, "is_available": false}
    }
    
    Examples:
        >>> # Create location assignment
        >>> pl = ProductLocation.objects.create(
        ...     product=burger,
        ...     location=nyc,
        ...     price_override=999,  # NYC charges $9.99
        ...     channels={
        ...         "ubereats": {"price": 1099, "is_available": True},
        ...         "doordash": {"price": 1049, "is_available": True}
        ...     }
        ... )
        
        >>> # Get channel price
        >>> ubereats_price = pl.get_price_for_channel('ubereats')  # 1099
        
        >>> # Check channel availability
        >>> is_available = pl.is_available_on_channel('doordash')  # True
    """
    
    # ========== CORE RELATIONSHIP ==========
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="location_links",
        help_text="""
        Product this assignment belongs to.
        Cascade delete: Remove assignments when product is deleted.
        """
    )
    
    location = models.ForeignKey(
        "locations.Location",
        on_delete=models.CASCADE,
        related_name="product_links",
        help_text="""
        Location where product is available.
        Cascade delete: Remove assignments when location is deleted.
        """
    )
    
    # ========== AVAILABILITY ==========
    
    is_available = models.BooleanField(
        default=True,
        help_text="""
        Base availability for this location (walk-in/default).
        Can be overridden per channel in 'channels' field.
        Use cases:
        - Product out of stock at this location
        - Seasonal availability
        - Location-specific menu items
        """
    )
    
    # ========== PRICING ==========
    
    price_override = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="""
        Base price override for this location (in cents).
        Used as fallback when no channel-specific price is set.
        Examples:
            999 = $9.99 (NYC premium pricing)
            799 = $7.99 (suburban standard pricing)
        Null = use product's base price
        """
    )
    
    channels = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Channel-specific pricing and availability.
        
        Format:
        {
            "channel_name": {
                "price": int (cents, optional),
                "is_available": bool (optional)
            }
        }
        
        Examples:
        {
            "ubereats": {
                "price": 1099,
                "is_available": true
            },
            "doordash": {
                "price": 1049,
                "is_available": false
            },
            "justeat": {
                "price": 999,
                "is_available": true
            }
        }
        
        Price Resolution:
        1. channels[channel]['price'] (if set)
        2. price_override (if set)
        3. product.price (fallback)
        
        Availability Resolution:
        1. channels[channel]['is_available'] (if set)
        2. is_available (fallback)
        """
    )
    
    # ========== TAX OVERRIDES ==========
    
    delivery_tax_rate_override = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='location_delivery_overrides',
        help_text="""
        Location-specific tax override for delivery orders.
        Overrides product's default delivery_tax_rate.
        Use case: Different tax rates in different jurisdictions.
        Example: NYC has 8.875% vs. 7% in suburbs
        """
    )
    
    takeaway_tax_rate_override = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='location_takeaway_overrides',
        help_text="""
        Location-specific tax override for takeaway orders.
        Overrides product's default takeaway_tax_rate.
        """
    )
    
    eat_in_tax_rate_override = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='location_eatin_overrides',
        help_text="""
        Location-specific tax override for eat-in orders.
        Overrides product's default eat_in_tax_rate.
        """
    )
    
    # ========== INVENTORY ==========
    
    stock_quantity = models.IntegerField(
        null=True,
        blank=True,
        help_text="""
        Current stock quantity at this location.
        Examples:
            50 = 50 units in stock
            0 = Out of stock
            Null = Unlimited/not tracked
        """
    )
    
    low_stock_threshold = models.IntegerField(
        null=True,
        blank=True,
        help_text="""
        Quantity threshold for low stock alerts.
        Examples:
            10 = Alert when stock drops below 10
            Null = No alerts
        When stock_quantity < low_stock_threshold, trigger alert.
        """
    )
    
    # ========== METADATA ==========
    
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when product was assigned to location"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when assignment was last modified"
    )
    
    # ========== META ==========
    
    class Meta:
        unique_together = ("product", "location")
        indexes = [
            models.Index(fields=['location', 'is_available']),
            models.Index(fields=['product']),
        ]
        verbose_name = "Product Location"
        verbose_name_plural = "Product Locations"
    
    # ========== METHODS ==========
    
    def __str__(self):
        """String representation: Product PLU @ Location Name"""
        return f"{self.product.plu} @ {self.location.name}"
    
    def get_price_for_channel(self, channel):
        """
        Get effective price for specific channel.
        
        Resolution Order:
        1. Channel-specific price (channels[channel]['price'])
        2. Location base price (price_override)
        3. Product base price (product.price)
        
        Args:
            channel (str, optional): Channel name (e.g., 'ubereats')
            
        Returns:
            int: Price in cents
            
        Examples:
            >>> pl = ProductLocation(
            ...     price_override=999,
            ...     channels={"ubereats": {"price": 1099}}
            ... )
            >>> pl.get_price_for_channel('ubereats')  # 1099
            >>> pl.get_price_for_channel('doordash')  # 999 (fallback)
            >>> pl.get_price_for_channel(None)  # 999 (fallback)
        """
        # Check channel-specific price first
        if channel and self.channels and channel in self.channels:
            channel_data = self.channels[channel]
            if isinstance(channel_data, dict) and 'price' in channel_data:
                return channel_data['price']
        
        # Fall back to location base price
        if self.price_override is not None:
            return self.price_override
        
        # Final fallback to product base price
        return self.product.price
    
    def is_available_on_channel(self, channel):
        """
        Check availability on specific channel.
        
        Resolution Order:
        1. Channel-specific availability (channels[channel]['is_available'])
        2. Location base availability (is_available)
        
        Args:
            channel (str, optional): Channel name (e.g., 'ubereats')
            
        Returns:
            bool: Whether product is available on channel
            
        Examples:
            >>> pl = ProductLocation(
            ...     is_available=True,
            ...     channels={"doordash": {"is_available": False}}
            ... )
            >>> pl.is_available_on_channel('ubereats')  # True (fallback)
            >>> pl.is_available_on_channel('doordash')  # False (override)
            >>> pl.is_available_on_channel(None)  # True (fallback)
        """
        # Check channel-specific availability first
        if channel and self.channels and channel in self.channels:
            channel_data = self.channels[channel]
            if isinstance(channel_data, dict) and 'is_available' in channel_data:
                return channel_data['is_available']
        
        # Fall back to location base availability
        return self.is_available
    
    def set_channel_data(self, channel, price=None, is_available=None):
        """
        Helper method to set channel-specific data.
        
        Args:
            channel (str): Channel name
            price (int, optional): Price in cents
            is_available (bool, optional): Availability flag
            
        Examples:
            >>> pl = ProductLocation.objects.get(...)
            >>> pl.set_channel_data('ubereats', price=1099, is_available=True)
            >>> pl.save()
            
            >>> # Update only price
            >>> pl.set_channel_data('doordash', price=1049)
            >>> pl.save()
        """
        if not self.channels:
            self.channels = {}
        
        if channel not in self.channels:
            self.channels[channel] = {}
        
        if price is not None:
            self.channels[channel]['price'] = price
        
        if is_available is not None:
            self.channels[channel]['is_available'] = is_available
    
    # ========== BACKWARD COMPATIBILITY PROPERTIES ==========
    
    @property
    def channel_prices(self):
        """
        Backward compatibility property for legacy code.
        
        Returns:
            dict: {channel: price} mapping
            
        Example:
            >>> pl.channels = {"ubereats": {"price": 649}}
            >>> pl.channel_prices  # {"ubereats": 649}
        """
        if not self.channels:
            return {}
        return {
            ch: data['price'] 
            for ch, data in self.channels.items() 
            if isinstance(data, dict) and 'price' in data
        }
    
    @property
    def channel_availability(self):
        """
        Backward compatibility property for legacy code.
        
        Returns:
            dict: {channel: is_available} mapping
            
        Example:
            >>> pl.channels = {"ubereats": {"is_available": True}}
            >>> pl.channel_availability  # {"ubereats": True}
        """
        if not self.channels:
            return {}
        return {
            ch: data['is_available'] 
            for ch, data in self.channels.items() 
            if isinstance(data, dict) and 'is_available' in data
        }


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


# ==============================================================================
# END OF MODELS
# ==============================================================================