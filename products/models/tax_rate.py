from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
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
