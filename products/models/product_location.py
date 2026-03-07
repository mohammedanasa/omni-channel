from django.db import models
from django.core.validators import MinValueValidator

from django.utils.translation import gettext_lazy as _
from common.models import BaseUUIDModel
from .product import Product
from .tax_rate import TaxRate



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
