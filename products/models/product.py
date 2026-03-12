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
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from common.models import BaseUUIDModel
from .tax_rate import TaxRate
from .category import Category




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

    managed_by = models.CharField(
        max_length=50,
        blank=True,
        default="internal_pos",
        help_text=(
            "Channel slug of the system that owns this product's core data. "
            "'internal_pos' = created locally or seeded from a marketplace. "
            "Any other value matches a Channel.slug where channel_type='pos' "
            "(e.g. 'clover', 'square'). Stamped by pull_and_persist()."
        ),
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
        from .product_location import ProductLocation
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
        from .product_location import ProductLocation
        if location:
            try:
                pl = ProductLocation.objects.get(product=self, location=location)
                # Use ProductLocation's method to handle channel logic
                return pl.get_price_for_channel(channel)
            except ProductLocation.DoesNotExist:
                pass  # Fall through to base price
        
        return self.price



# ==============================================================================
# END OF MODELS
# ==============================================================================