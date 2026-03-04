"""
Django Admin Configuration for Products
========================================

Compatible with django-tenants:
- TaxRate, Category, Product models visible in tenant admin
- Proper filters and search
- Inline editing for relationships
- Color-coded product types
"""

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import (
    Product,
    Category,
    TaxRate,
    ProductRelation,
    Product
)
from locations.models import Location


# # ============================================================================
# # Inline Admins
# # ============================================================================

# class ProductRelationInline(admin.TabularInline):
#     """Inline for sub-products"""
#     model = ProductRelation
#     fk_name = 'parent'
#     extra = 0
#     fields = ['child', 'sort_order', 'auto_apply']
#     autocomplete_fields = ['child']
#     verbose_name = "Sub-Product"
#     verbose_name_plural = "Sub-Products"


# class ProductInline(admin.TabularInline):
#     """Inline for  assignments"""
#     model = Product
#     extra = 0
#     fields = [
#         '',
#         'is_available',
#         'price_override',
#         'channel_prices',
#         'delivery_tax_rate_override',
#         'stock_quantity'
#     ]
#     autocomplete_fields = ['', 'delivery_tax_rate_override']
#     verbose_name = " Assignment"
#     verbose_name_plural = " Assignments"


# # ============================================================================
# # TaxRate Admin
# # ============================================================================

# @admin.register(TaxRate)
# class TaxRateAdmin(admin.ModelAdmin):
#     """TaxRate admin"""
    
#     list_display = [
#         'name',
#         'display_value',
#         'is_default_badge',
#         'is_active',
#         'usage_count',
#         'created_at',
#     ]
#     list_filter = ['is_default', 'is_active', 'created_at']
#     search_fields = ['name', 'description']
#     readonly_fields = ['id', 'created_at', 'updated_at']
    
#     fieldsets = (
#         ('Identification', {
#             'fields': ('id', 'name', 'description')
#         }),
#         ('Tax Configuration', {
#             'fields': ('percentage', 'flat_fee'),
#             'description': 'Choose EITHER percentage OR flat_fee (not both)'
#         }),
#         ('Settings', {
#             'fields': ('is_default', 'is_active')
#         }),
#         ('Metadata', {
#             'fields': ('created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     def display_value(self, obj):
#         """Display formatted value"""
#         if obj.percentage is not None:
#             return f"{obj.percentage / 1000:.3f}%"
#         elif obj.flat_fee is not None:
#             return f"${obj.flat_fee / 100:.2f}"
#         return "—"
#     display_value.short_description = 'Value'
    
#     def is_default_badge(self, obj):
#         """Display default badge"""
#         if obj.is_default:
#             return format_html(
#                 '<span style="background-color: #28a745; color: white; '
#                 'padding: 3px 10px; border-radius: 3px; font-size: 11px;">'
#                 '✓ DEFAULT</span>'
#             )
#         return format_html('<span style="color: #999;">—</span>')
#     is_default_badge.short_description = 'Default'
    
#     def usage_count(self, obj):
#         """Count products using this tax rate"""
#         count = (
#             obj.products_delivery.count() +
#             obj.products_takeaway.count() +
#             obj.products_eatin.count() +
#             obj._delivery_overrides.count() +
#             obj._takeaway_overrides.count() +
#             obj._eatin_overrides.count()
#         )
#         return count
#     usage_count.short_description = 'Usage'


# # ============================================================================
# # Category Admin
# # ============================================================================

# @admin.register(Category)
# class CategoryAdmin(admin.ModelAdmin):
#     """Category admin"""
    
#     list_display = [
#         'pos_category_id',
#         'name',
#         'sort_order',
#         'product_count',
#         'created_at',
#     ]
#     list_filter = ['created_at']
#     search_fields = ['pos_category_id', 'name', 'description']
#     readonly_fields = ['id', 'created_at', 'updated_at']
    
#     fieldsets = (
#         ('Identification', {
#             'fields': ('id', 'pos_category_id')
#         }),
#         ('Information', {
#             'fields': (
#                 'name',
#                 'name_translations',
#                 'description',
#                 'description_translations',
#                 'image_url',
#                 'sort_order'
#             )
#         }),
#         ('Metadata', {
#             'fields': ('created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     def product_count(self, obj):
#         """Count products in category"""
#         return obj.products.count()
#     product_count.short_description = 'Products'


# # ============================================================================
# # Product Admin
# # ============================================================================

# @admin.register(Product)
# class ProductAdmin(admin.ModelAdmin):
#     """Product admin with full features"""
    
#     list_display = [
#         'plu',
#         'name',
#         'product_type_badge',
#         'price_display',
#         'visible_badge',
#         'is_active',
#         'category_count',
#         '_count',
#         'created_at',
#     ]
#     list_filter = [
#         'product_type',
#         'visible',
#         'is_active',
#         'is_combo',
#         'categories',
#         'created_at',
#     ]
#     search_fields = ['plu', 'name', 'kitchen_name', 'description']
#     readonly_fields = ['id', 'plu', 'created_at', 'updated_at']
#     autocomplete_fields = [
#         'categories',
#         'delivery_tax_rate',
#         'takeaway_tax_rate',
#         'eat_in_tax_rate'
#     ]
    
#     fieldsets = (
#         ('Identification', {
#             'fields': ('id', 'plu', 'pos_product_id', 'gtin'),
#             'description': 'PLU is auto-generated on creation'
#         }),
#         ('Basic Information', {
#             'fields': (
#                 'name',
#                 'name_translations',
#                 'kitchen_name',
#                 'description',
#                 'description_translations',
#                 'image_url'
#             )
#         }),
#         ('Product Type & Flags', {
#             'fields': (
#                 'product_type',
#                 'is_combo',
#                 'is_variant',
#                 'is_variant_group',
#                 'visible',
#                 'channel_overrides'
#             )
#         }),
#         ('Pricing', {
#             'fields': (
#                 'price',
#                 'overloads',
#                 'bottle_deposit_price'
#             )
#         }),
#         ('Tax Rates', {
#             'fields': (
#                 'delivery_tax_rate',
#                 'takeaway_tax_rate',
#                 'eat_in_tax_rate'
#             ),
#             'description': 'Default tax rates (can be overridden per )'
#         }),
#         ('Selection Rules (Groups Only)', {
#             'fields': (
#                 'min_select',
#                 'max_select',
#                 'multi_max',
#                 'max_free',
#                 'default_quantity',
#                 'sort_order'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Categories & Auto-Apply', {
#             'fields': ('categories', 'auto_apply')
#         }),
#         ('Nutrition & Tags', {
#             'fields': (
#                 'calories',
#                 'calories_range_high',
#                 'nutritional_info',
#                 'beverage_info',
#                 'packaging',
#                 'supplemental_info',
#                 'product_tags'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Metadata', {
#             'fields': ('is_active', 'created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     inlines = [ProductRelationInline, ProductInline]
    
#     def product_type_badge(self, obj):
#         """Color-coded type badge"""
#         colors = {
#             1: '#28a745',  # Green - Main
#             2: '#007bff',  # Blue - Modifier
#             3: '#ffc107',  # Yellow - Group
#             4: '#dc3545',  # Red - Bundle
#         }
#         return format_html(
#             '<span style="background-color: {}; color: white; '
#             'padding: 3px 10px; border-radius: 3px; font-size: 11px;">{}</span>',
#             colors.get(obj.product_type, '#6c757d'),
#             obj.get_product_type_display()
#         )
#     product_type_badge.short_description = 'Type'
    
#     def price_display(self, obj):
#         """Display formatted price"""
#         return f"${obj.price / 100:.2f}"
#     price_display.short_description = 'Price'
    
#     def visible_badge(self, obj):
#         """Display visibility badge"""
#         if obj.visible:
#             return format_html('<span style="color: green;">✓ Visible</span>')
#         return format_html('<span style="color: red;">✗ Hidden</span>')
#     visible_badge.short_description = 'Visibility'
    
#     def category_count(self, obj):
#         """Count categories"""
#         return obj.categories.count()
#     category_count.short_description = 'Categories'
    
#     def _count(self, obj):
#         """Count s"""
#         return obj.s.count()
#     _count.short_description = 's'
    
#     def get_queryset(self, request):
#         """Optimize queries"""
#         qs = super().get_queryset(request)
#         return qs.prefetch_related('categories', 's').annotate(
#             num_categories=Count('categories', distinct=True),
#             num_s=Count('s', distinct=True)
#         )


# # ============================================================================
# # Product Admin (optional - usually managed via inline)
# # ============================================================================

# # @admin.register(Product)
# # class ProductAdmin(admin.ModelAdmin):
# #     """Product admin for direct management"""
    
# #     list_display = [
# #         'product_plu',
# #         '_name',
# #         'is_available_badge',
# #         'price_override_display',
# #         'has_channel_prices',
# #         'stock_quantity',
# #         'assigned_at',
# #     ]
# #     list_filter = ['is_available', 'assigned_at', '']
# #     search_fields = ['product__plu', 'product__name', '__name']
# #     readonly_fields = ['id', 'assigned_at', 'updated_at']
# #     autocomplete_fields = [
# #         'product',
# #         '',
# #         'delivery_tax_rate_override',
# #         'takeaway_tax_rate_override',
# #         'eat_in_tax_rate_override'
# #     ]
    
# #     fieldsets = (
# #         ('Assignment', {
# #             'fields': ('id', 'product', '')
# #         }),
# #         ('Availability & Pricing', {
# #             'fields': (
# #                 'is_available',
# #                 'price_override',
# #                 'channel_prices',
# #                 'channel_availability'
# #             )
# #         }),
# #         ('Tax Rate Overrides', {
# #             'fields': (
# #                 'delivery_tax_rate_override',
# #                 'takeaway_tax_rate_override',
# #                 'eat_in_tax_rate_override'
# #             ),
# #             'classes': ('collapse',)
# #         }),
# #         ('Inventory', {
# #             'fields': (
# #                 'stock_quantity',
# #                 'low_stock_threshold'
# #             ),
# #             'classes': ('collapse',)
# #         }),
# #         ('Metadata', {
# #             'fields': ('assigned_at', 'updated_at'),
# #             'classes': ('collapse',)
# #         }),
# #     )
    
# #     def product_plu(self, obj):
# #         return obj.product.plu
# #     product_plu.short_description = 'Product PLU'
# #     product_plu.admin_order_field = 'product__plu'
    
# #     def _name(self, obj):
# #         return obj.name
# #     _name.short_description = ''
# #     _name.admin_order_field = '__name'
    
# #     def is_available_badge(self, obj):
# #         if obj.is_available:
# #             return format_html('<span style="color: green;">✓ Available</span>')
# #         return format_html('<span style="color: red;">✗ Unavailable</span>')
# #     is_available_badge.short_description = 'Availability'
    
# #     def price_override_display(self, obj):
# #         if obj.price_override is not None:
# #             return f"${obj.price_override / 100:.2f}"
# #         return "—"
# #     price_override_display.short_description = 'Price Override'
    
# #     def has_channel_prices(self, obj):
# #         if obj.channel_prices:
# #             return format_html(
# #                 '<span style="color: blue;">{} channels</span>',
# #                 len(obj.channel_prices)
# #             )
# #         return "—"
# #     has_channel_prices.short_description = 'Channel Prices'


# # ============================================================================
# # ProductRelation Admin (optional)
# # ============================================================================

# @admin.register(ProductRelation)
# class ProductRelationAdmin(admin.ModelAdmin):
#     """ProductRelation admin for direct management"""
    
#     list_display = [
#         'parent_plu',
#         'child_plu',
#         'sort_order',
#         'auto_apply',
#     ]
#     list_filter = ['auto_apply']
#     search_fields = ['parent__plu', 'child__plu']
#     autocomplete_fields = ['parent', 'child']
    
#     def parent_plu(self, obj):
#         return obj.parent.plu
#     parent_plu.short_description = 'Parent PLU'
#     parent_plu.admin_order_field = 'parent__plu'
    
#     def child_plu(self, obj):
#         return obj.child.plu
#     child_plu.short_description = 'Child PLU'
#     child_plu.admin_order_field = 'child__plu'


# ==================================================================
# DJANGO-TENANTS COMPATIBILITY NOTES
# ==================================================================
#
# These admin classes work with django-tenants because:
#
# 1. Models are in TENANT_APPS (not SHARED_APPS)
# 2. Admin is automatically scoped to current tenant schema
# 3. No special configuration needed
#
# To access admin:
# 1. Login to tenant domain (e.g., mcdonalds.yourdomain.com/admin)
# 2. Models appear automatically in tenant admin
#
# NOTE: If you want these models in SHARED schema instead:
# 1. Move models to SHARED_APPS in settings.py
# 2. Create TenantAwareModelAdmin base class
# 3. Filter querysets by current tenant
#
# ==================================================================