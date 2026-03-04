"""
Products URL Configuration
===========================
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet,
    CategoryViewSet,
    TaxRateViewSet,
)

app_name = 'products'

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'tax-rates', TaxRateViewSet, basename='taxrate')

urlpatterns = [
    path('', include(router.urls)),
]

# ==================================================================
# GENERATED ENDPOINTS
# ==================================================================
#
# PRODUCTS:
# GET    /api/products/                          - List products
# POST   /api/products/                          - Create product
# GET    /api/products/{plu}/                    - Get product
# PUT    /api/products/{plu}/                    - Update product
# PATCH  /api/products/{plu}/                    - Partial update
# DELETE /api/products/{plu}/                    - Delete product
# POST   /api/products/bulk_sync/                - Bulk sync
# GET    /api/products/export_menu/              - Export menu
# POST   /api/products/mark_unavailable/         - Mark unavailable
# PATCH  /api/products/{plu}/update_location_pricing/ - Update pricing
#
# CATEGORIES:
# GET    /api/categories/                        - List categories
# POST   /api/categories/                        - Create category
# GET    /api/categories/{pos_category_id}/      - Get category
# PUT    /api/categories/{pos_category_id}/      - Update category
# PATCH  /api/categories/{pos_category_id}/      - Partial update
# DELETE /api/categories/{pos_category_id}/      - Delete category
#
# TAX RATES:
# GET    /api/tax-rates/                         - List tax rates
# POST   /api/tax-rates/                         - Create tax rate
# GET    /api/tax-rates/{id}/                    - Get tax rate
# PUT    /api/tax-rates/{id}/                    - Update tax rate
# PATCH  /api/tax-rates/{id}/                    - Partial update
# DELETE /api/tax-rates/{id}/                    - Delete tax rate
#
# ==================================================================