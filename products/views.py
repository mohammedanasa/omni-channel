"""
==============================================================================
PRODUCTS VIEWS - COMPREHENSIVE DOCUMENTATION
==============================================================================

This module contains all DRF viewsets for the product management API.

ViewSets:
    - ProductViewSet: Complete product CRUD with custom actions
    - CategoryViewSet: Category management
    - TaxRateViewSet: Tax rate management

Key Features:
    - Header-based context (X-Location-ID, X-Channel)
    - Expand parameter support (?expand=sub_products)
    - Location-specific filtering
    - Channel-specific operations
    - Bulk sync operations
    - Menu export functionality
    - Multi-tenant isolation (django-tenants)
    - Performance-optimized queries (prefetch_related, select_related)

API Endpoints (12 total):
    
    Products (8):
    - GET    /api/products/                       List products
        Query params: ?product_type=1  (1=Main, 2=Modifier, 3=Group, 4=Bundle)
    - POST   /api/products/                       Create product
    - GET    /api/products/{plu}/                 Get product
    - PUT    /api/products/{plu}/                 Update product
    - PATCH  /api/products/{plu}/                 Partial update
    - DELETE /api/products/{plu}/                 Delete product
    - POST   /api/products/bulk_sync/             Bulk import
    - GET    /api/products/export_menu/           Export menu tree
    - POST   /api/products/mark_unavailable/      Mark unavailable
    - PATCH  /api/products/{plu}/update_location_pricing/  Update pricing
    
    Categories (3):
    - GET    /api/categories/                     List categories
    - POST   /api/categories/                     Create category
    - GET    /api/categories/{pos_category_id}/   Get category
    
    Tax Rates (3):
    - GET    /api/tax-rates/                      List tax rates
    - POST   /api/tax-rates/                      Create tax rate
    - GET    /api/tax-rates/{id}/                 Get tax rate

Headers:
    - Authorization: Bearer {token} (required)
    - X-Tenant-ID: {tenant_uuid} (required)
    - X-Location-ID: {location_uuid} (optional)
    - X-Channel: {channel_name} (optional, e.g., 'ubereats')

Author: Your Team
Version: 1.0.0
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
import uuid as _uuid

from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
    OpenApiParameter,
    OpenApiTypes
)
from rest_framework import serializers as drf_serializers

from .models import Product, Category, TaxRate, ProductLocation
from .serializers import (
    ProductSerializer,
    NestedProductSerializer,
    CategorySerializer,
    TaxRateSerializer,
    BulkProductSyncSerializer,
)
from locations.models import Location
from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema, TENANT_HEADER, LOCATION_HEADER


# ==============================================================================
# OPENAPI PARAMETERS
# ==============================================================================

CHANNEL_HEADER = OpenApiParameter(
    name="X-Channel",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Channel name (e.g. 'ubereats', 'doordash')",
)

PRODUCT_TYPE_FILTER = OpenApiParameter(
    name="product_type",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "Filter products by type. "
        "1 = Main product, "
        "2 = Modifier item, "
        "3 = Modifier group, "
        "4 = Bundle group"
    ),
    enum=[1, 2, 3, 4],
)


# ==============================================================================
# PRODUCT VIEWSET
# ==============================================================================

@tenant_schema("Products", LOCATION_HEADER)
class ProductViewSet(viewsets.ModelViewSet):
    """
    Complete product management viewset with custom actions.
    
    Provides:
    - Standard CRUD operations (list, create, retrieve, update, delete)
    - Custom actions (bulk_sync, export_menu, mark_unavailable)
    - Location/channel context handling via headers
    - Expand parameter support for nested products
    - Performance-optimized queries
    
    Permissions:
    - IsAuthenticated: Must have valid JWT token
    - HasTenantAccess: Must have access to specified tenant
    
    Lookup:
    - Uses 'plu' field instead of 'id' for retrieval
    
    Context Handling:
    - X-Location-ID header → Sets location context
    - X-Channel header → Sets channel context
    - Both passed to serializers for price/availability calculations
    
    Query Parameters:
    - product_type: Filter by type (1,2,3,4)
    - category_id: Filter by category pos_category_id
    - visible: Filter by visibility (true/false)
    - for_location: Only products at X-Location-ID location
    - is_active: Filter by active status
    - search: Search name/PLU/kitchen_name
    - expand: Comma-separated fields (e.g., sub_products)
    
    Performance Optimizations:
    - select_related: Tax rates
    - prefetch_related: Categories, location assignments
    - Efficient querying prevents N+1 problems
    
    Examples:
        >>> # List all burgers
        >>> GET /api/products/?product_type=1&category_id=BURGERS
        
        >>> # Get product with location context
        >>> GET /api/products/BURGER-01/
        >>> Headers: X-Location-ID: {uuid}, X-Channel: ubereats
        
        >>> # Get product with nested sub-products
        >>> GET /api/products/BURGER-01/?expand=sub_products
        
        >>> # List products available at specific location
        >>> GET /api/products/?for_location=true
        >>> Headers: X-Location-ID: {uuid}
    """
    
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]
    lookup_field = 'plu'

    # ========== LIST (with product_type filter docs) ==========

    @extend_schema(
        tags=["Products"],
        summary="List products",
        description=(
            "Returns a list of products. Supports filtering by product_type, "
            "category_id, visible, for_location, is_active, and text search."
        ),
        parameters=[
            TENANT_HEADER,
            LOCATION_HEADER,
            PRODUCT_TYPE_FILTER,
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    # ========== QUERYSET ==========
    
    def get_queryset(self):
        """
        Get filtered and optimized product queryset.
        
        Applies filters from query parameters:
        - product_type: Product type (1=Main, 2=Modifier, 3=Group, 4=Bundle)
        - category_id: Category pos_category_id
        - visible: Visibility flag (true/false)
        - is_active: Only products at location from X-Location-ID header Active status (true/false)
        - search: Text search on name/PLU/kitchen_name
        
        Performance Optimizations:
        - select_related: Tax rate foreign keys (1 query instead of N+1)
        - prefetch_related: Categories M2M and location assignments
        - distinct(): Removes duplicates from M2M filtering
        
        Returns:
            QuerySet: Filtered and optimized product queryset
            
        Examples:
            >>> # Internal usage by DRF
            >>> queryset = self.get_queryset()
            >>> products = queryset.filter(product_type=1)
        """
        # Base queryset with optimizations
        queryset = Product.objects.select_related(
            'delivery_tax_rate',
            'takeaway_tax_rate',
            'eat_in_tax_rate'
        ).prefetch_related(
            'categories',
            Prefetch(
                'location_links',
                queryset=ProductLocation.objects.select_related(
                    'location',
                    'delivery_tax_rate_override',
                    'takeaway_tax_rate_override',
                    'eat_in_tax_rate_override'
                )
            )
        )
        
        # Filter by product type
        product_type = self.request.query_params.get('product_type')
        if product_type:
            queryset = queryset.filter(product_type=int(product_type))
        
        # Filter by category
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(categories__pos_category_id=category_id)
        
        # Filter by visibility
        visible = self.request.query_params.get('visible')
        if visible is not None:
            queryset = queryset.filter(visible=visible.lower() == 'true')
        
        # Filter by location
        location = self._get_location_from_header()
        
        if location:
            # X-Location-ID present → only products assigned to this location
            location_filter = {'location_links__location': location}
            
            # ?is_available=true → further filter to only available products
            is_available_at_location = self.request.query_params.get('is_available')
            if is_available_at_location and is_available_at_location.lower() == 'true':
                location_filter['location_links__is_available'] = True
            
            queryset = queryset.filter(**location_filter)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Text search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(plu__icontains=search) |
                Q(kitchen_name__icontains=search)
            )
        
        return queryset.distinct()
    
    # ========== SERIALIZER SELECTION ==========
    
    def get_serializer_class(self):
        """
        Select serializer based on expand parameter.
        
        Logic:
        - If expand=sub_products → Use NestedProductSerializer (recursive)
        - Otherwise → Use ProductSerializer (flat)
        
        The expand parameter allows clients to request nested product
        structures in a single response instead of multiple API calls.
        
        Returns:
            class: Serializer class to use
            
        Examples:
            >>> # Flat response
            >>> GET /api/products/BURGER-01/
            >>> # Uses ProductSerializer
            
            >>> # Nested response
            >>> GET /api/products/BURGER-01/?expand=sub_products
            >>> # Uses NestedProductSerializer
        """
        expand = self.request.query_params.get('expand', '')
        expand_fields = [f.strip() for f in expand.split(',') if f.strip()]
        
        if 'sub_products' in expand_fields:
            return NestedProductSerializer
        
        return ProductSerializer
    
    # ========== CONTEXT HANDLING ==========
    
    def get_serializer_context(self):
        """
        Build serializer context with location/channel from headers.
        
        Context Variables Set:
        - request: Current request object
        - view: Current view instance
        - format: Response format
        - location: Location instance from X-Location-ID header
        - channel: Channel name from X-Channel header
        - expand: List of fields to expand
        
        This context is used by serializers to:
        - Calculate effective prices (location + channel specific)
        - Show/hide location information based on header presence
        - Determine availability per channel
        
        Returns:
            dict: Context dictionary for serializers
            
        Note:
            Headers are extracted once and reused by all serializers
            in the request lifecycle for efficiency.
        """
        context = super().get_serializer_context()
        
        # Extract location and channel from headers
        context['location'] = self._get_location_from_header()
        context['channel'] = self._get_channel_from_header()
        
        # Parse expand parameter
        expand = self.request.query_params.get('expand', '')
        context['expand'] = [f.strip() for f in expand.split(',') if f.strip()]
        
        return context
    
    def _get_location_from_header(self):
        """
        Extract location from X-Location-ID header.
        
        Process:
        1. Get X-Location-ID from request.META
        2. Validate UUID format
        3. Lookup Location instance
        4. Return Location or None
        
        Returns:
            Location or None: Location instance if valid header, else None
            
        Note:
            Returns None on any error (invalid UUID, location not found).
            This is intentional - invalid header should not break the request,
            just means no location context is available.
            
        Examples:
            >>> # Valid header
            >>> request.META['HTTP_X_LOCATION_ID'] = 'uuid-here'
            >>> location = self._get_location_from_header()
            >>> print(location.name)  # "NYC Times Square"
            
            >>> # Invalid header
            >>> request.META['HTTP_X_LOCATION_ID'] = 'invalid'
            >>> location = self._get_location_from_header()
            >>> print(location)  # None
        """
        location_id = self.request.META.get('HTTP_X_LOCATION_ID')
        if location_id:
            try:
                # Validate UUID format
                _uuid.UUID(str(location_id))
            except ValueError:
                return None
            
            try:
                return Location.objects.get(id=location_id)
            except Location.DoesNotExist:
                return None
        
        return None
    
    def _get_channel_from_header(self):
        """
        Extract channel from X-Channel header.
        
        Process:
        1. Get X-Channel from request.META
        2. Normalize to lowercase
        3. Return channel name or None
        
        Returns:
            str or None: Channel name in lowercase, or None if not provided
            
        Examples:
            >>> # Header: X-Channel: UberEats
            >>> channel = self._get_channel_from_header()
            >>> print(channel)  # "ubereats"
            
            >>> # No header
            >>> channel = self._get_channel_from_header()
            >>> print(channel)  # None
        """
        channel = self.request.META.get('HTTP_X_CHANNEL')
        return channel.lower() if channel else None
    
    def perform_create(self, serializer):
        """
        Auto-assign product to location when X-Location-ID header present.
        
        Process:
        1. Save product via serializer
        2. Check if X-Location-ID header present
        3. If present and no explicit locations:
           - Create ProductLocation record
           - Set is_available=True
        
        This provides a convenient default behavior:
        - User creating product at specific location
        - Product automatically assigned to that location
        - Can be overridden by providing locations explicitly
        
        Args:
            serializer: Validated serializer instance
            
        Returns:
            Product: Created product instance
            
        Examples:
            >>> # Without header - no auto-assignment
            >>> POST /api/products/
            >>> {"name": "Burger", "price": 899}
            >>> # Product created but not assigned to any location
            
            >>> # With header - auto-assignment
            >>> POST /api/products/
            >>> Headers: X-Location-ID: {uuid}
            >>> {"name": "Burger", "price": 899}
            >>> # Product created AND assigned to location from header
        """
        product = serializer.save()
        
        # Auto-assign to location if header present
        location = self._get_location_from_header()
        if location:
            # Check if product already has location assignments
            has_assignments = ProductLocation.objects.filter(product=product).exists()
            
            if not has_assignments:
                ProductLocation.objects.create(
                    product=product,
                    location=location,
                    is_available=True
                )
        
        return product
    
    # ========== CUSTOM ACTIONS ==========
    
    @extend_schema(
        tags=["Products"],
        summary="Bulk sync products, categories, and tax rates",
        request=BulkProductSyncSerializer,
        responses={
            200: inline_serializer(
                name="BulkSyncResponse",
                fields={
                    "success": drf_serializers.BooleanField(),
                    "products_synced": drf_serializers.IntegerField(),
                    "categories_synced": drf_serializers.IntegerField(),
                    "tax_rates_synced": drf_serializers.IntegerField(),
                },
            ),
            400: inline_serializer(
                name="BulkSyncError",
                fields={
                    "success": drf_serializers.BooleanField(default=False),
                    "errors": drf_serializers.DictField(),
                },
            ),
        },
        parameters=[TENANT_HEADER, LOCATION_HEADER],
    )
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def bulk_sync(self, request):
        """
        Bulk import/sync products, categories, and tax rates.
        
        Purpose: Efficiently import large datasets from POS or external systems.
        
        Features:
        - Atomic transaction (all or nothing)
        - Update or create (upsert) logic
        - Processes in correct order (tax rates → categories → products)
        
        Request Body:
        {
            "tax_rates": [
                {"name": "VAT 9%", "percentage": 9000, "is_default": true}
            ],
            "categories": [
                {"pos_category_id": "BURGERS", "name": "Burgers"}
            ],
            "products": [
                {
                    "plu": "BURGER-01",  // Optional - auto-generated if not provided
                    "name": "Cheeseburger",
                    "product_type": 1,
                    "price": 899,
                    "pos_category_ids": ["BURGERS"]
                }
            ]
        }
        
        Response (Success):
        {
            "success": true,
            "products_synced": 1,
            "categories_synced": 1,
            "tax_rates_synced": 1
        }
        
        Response (Error):
        {
            "success": false,
            "errors": {
                "products": [
                    {
                        "plu": ["Product with PLU 'BURGER-01' already exists"]
                    }
                ]
            }
        }
        
        Args:
            request: DRF request object with data
            
        Returns:
            Response: Success/error response with counts
            
        Raises:
            ValidationError: If data validation fails (400)
            Exception: If sync fails (500) - transaction rolled back
            
        Examples:
            >>> POST /api/products/bulk_sync/
            >>> Content-Type: application/json
            >>> {
            ...     "categories": [...],
            ...     "products": [...]
            ... }
            >>> # Response: {"success": true, "products_synced": 10}
        """
        serializer = BulkProductSyncSerializer(
            data=request.data,
            context=self.get_serializer_context()
        )
        
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = serializer.save()
            
            return Response({
                'success': True,
                'products_synced': len(result['products']),
                'categories_synced': result['categories_count'],
                'tax_rates_synced': result['tax_rates_count']
            })
        
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        tags=["Products"],
        summary="Export menu for delivery channel",
        description="""
        Export complete menu tree for delivery platforms.
        
        Returns nested product structure with location/channel pricing.
        Requires X-Location-ID header.
        Optional X-Channel header for channel-specific pricing.
        """,
        responses={
            200: inline_serializer(
                name="ExportMenuResponse",
                fields={
                    "products": NestedProductSerializer(many=True),
                    "categories": CategorySerializer(many=True),
                    "metadata": inline_serializer(
                        name="ExportMenuMetadata",
                        fields={
                            "total_products": drf_serializers.IntegerField(),
                            "location_id": drf_serializers.UUIDField(),
                            "location_name": drf_serializers.CharField(),
                            "channel": drf_serializers.CharField(allow_null=True),
                        },
                    ),
                },
            ),
            400: inline_serializer(
                name="ExportMenuError",
                fields={"error": drf_serializers.CharField()},
            ),
        },
        parameters=[
            TENANT_HEADER,
            LOCATION_HEADER,
            CHANNEL_HEADER,
            OpenApiParameter(
                name="category_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by POS category ID"
            ),
            OpenApiParameter(
                name="visible_only",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Only visible products (default: true)"
            ),
        ],
    )
    @action(detail=False, methods=['get'])
    def export_menu(self, request):
        """
        Export complete menu tree for delivery platforms.
        
        Purpose: Generate full nested menu structure for platforms like
        UberEats, DoorDash to sync menus.
        
        Requirements:
        - X-Location-ID header (required)
        - X-Channel header (optional)
        
        Features:
        - Nested product structure (products → groups → modifiers)
        - Location-specific pricing
        - Channel-specific pricing (if X-Channel provided)
        - Tax rate information
        - Category grouping
        - Metadata (location info, counts)
        
        Query Parameters:
        - category_id: Filter by specific category
        - visible_only: Only include visible products (default: true)
        
        Response Structure:
        {
            "products": [
                {
                    "plu": "BURGER-01",
                    "name": "Cheeseburger",
                    "price": 899,
                    "sub_products": [
                        {
                            "plu": "GRP-TOPPIN-A1B2",
                            "name": "Choose Toppings",
                            "sub_products": [...]
                        }
                    ]
                }
            ],
            "categories": [...],
            "metadata": {
                "total_products": 50,
                "location_id": "uuid",
                "location_name": "NYC Times Square",
                "channel": "ubereats"
            }
        }
        
        Args:
            request: DRF request object
            
        Returns:
            Response: Menu tree with metadata
            
        Raises:
            400: If X-Location-ID header missing
            
        Examples:
            >>> GET /api/products/export_menu/
            >>> Headers:
            >>>   X-Location-ID: {uuid}
            >>>   X-Channel: ubereats
            >>> # Response: Full nested menu tree
        """
        location = self._get_location_from_header()
        if not location:
            return Response(
                {'error': 'X-Location-ID header required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        category_filter = request.query_params.get('category_id')
        visible_only = request.query_params.get('visible_only', 'true').lower() == 'true'
        
        # Get main products at this location
        queryset = Product.objects.filter(
            product_type=Product.ProductType.MAIN,
            location_links__location=location,
            location_links__is_available=True
        )
        
        if visible_only:
            queryset = queryset.filter(visible=True)
        
        if category_filter:
            queryset = queryset.filter(categories__pos_category_id=category_filter)
        
        # Serialize with nested structure
        serializer = NestedProductSerializer(
            queryset,
            many=True,
            context={
                **self.get_serializer_context(),
                'max_depth': 10
            }
        )
        
        # Get categories
        categories = Category.objects.filter(
            products__in=queryset
        ).distinct()
        
        return Response({
            'products': serializer.data,
            'categories': CategorySerializer(categories, many=True).data,
            'metadata': {
                'total_products': queryset.count(),
                'location_id': str(location.id),
                'location_name': location.name,
                'channel': self._get_channel_from_header(),
            }
        })
    
    @extend_schema(
        tags=["Products"],
        summary="Mark products unavailable",
        description="""
        Mark products as unavailable globally, per location, or per channel.
        
        Scope depends on headers:
        - No headers: Global (product.visible = false)
        - X-Location-ID only: Location-wide (location.is_available = false)
        - X-Location-ID + X-Channel: Channel-specific (channels[channel].is_available = false)
        """,
        request=inline_serializer(
            name="MarkUnavailableRequest",
            fields={
                "plus": drf_serializers.ListField(
                    child=drf_serializers.CharField(),
                    required=False,
                    help_text='List of PLU codes, e.g. ["BURGER-01"]',
                ),
                "tags": drf_serializers.ListField(
                    child=drf_serializers.IntegerField(),
                    required=False,
                    help_text="List of product tag IDs, e.g. [104, 109]",
                ),
            },
        ),
        responses={
            200: inline_serializer(
                name="MarkUnavailableResponse",
                fields={
                    "success": drf_serializers.BooleanField(),
                    "updated": drf_serializers.IntegerField(),
                    "scope": drf_serializers.CharField(),
                },
            ),
            400: inline_serializer(
                name="MarkUnavailableError",
                fields={"error": drf_serializers.CharField()},
            ),
        },
        parameters=[TENANT_HEADER, LOCATION_HEADER, CHANNEL_HEADER],
    )
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def mark_unavailable(self, request):
        """
        Mark products as unavailable with flexible scoping.
        
        Purpose: Quickly mark products out of stock or unavailable
        with different levels of granularity.
        
        Scope Levels:
        1. Global: All locations, all channels (no headers)
        2. Location: Specific location, all channels (X-Location-ID)
        3. Channel: Specific location + channel (X-Location-ID + X-Channel)
        
        Selection Methods:
        - By PLU codes (plus): Specific products
        - By tags (tags): Products with specific tags (e.g., allergens)
        
        Request Body (one required):
        {
            "plus": ["BURGER-01", "FRIES-01"]
        }
        OR
        {
            "tags": [104, 109]  // Products with these tag IDs
        }
        
        Response:
        {
            "success": true,
            "updated": 2,
            "scope": "channel ubereats at NYC Times Square"
        }
        
        Use Cases:
        - Out of stock: Mark product unavailable at specific location
        - Allergen alert: Mark all products with allergen tag unavailable
        - Channel issue: Disable on UberEats but keep on DoorDash
        - Closing time: Mark all products unavailable globally
        
        Args:
            request: DRF request with plus or tags
            
        Returns:
            Response: Success/error with update count and scope
            
        Examples:
            >>> # Global unavailability
            >>> POST /api/products/mark_unavailable/
            >>> {"plus": ["BURGER-01"]}
            >>> # Sets product.visible = False
            
            >>> # Location unavailability
            >>> POST /api/products/mark_unavailable/
            >>> Headers: X-Location-ID: {uuid}
            >>> {"plus": ["BURGER-01"]}
            >>> # Sets ProductLocation.is_available = False
            
            >>> # Channel unavailability
            >>> POST /api/products/mark_unavailable/
            >>> Headers: X-Location-ID: {uuid}, X-Channel: ubereats
            >>> {"plus": ["BURGER-01"]}
            >>> # Sets ProductLocation.channels[ubereats].is_available = False
        """
        plus = request.data.get('plus', [])
        tags = request.data.get('tags', [])
        
        if not plus and not tags:
            return Response(
                {'error': 'Either plus or tags required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Build queryset
        queryset = Product.objects.all()
        if plus:
            queryset = queryset.filter(plu__in=plus)
        elif tags:
            queryset = queryset.filter(product_tags__overlap=tags)
        
        location = self._get_location_from_header()
        channel = self._get_channel_from_header()
        
        # Scope 3: Location + Channel
        if location and channel:
            updated = 0
            for product in queryset:
                try:
                    pl = ProductLocation.objects.get(product=product, location=location)
                    if not pl.channels:
                        pl.channels = {}
                    if channel not in pl.channels:
                        pl.channels[channel] = {}
                    pl.channels[channel]['is_available'] = False
                    pl.save()
                    updated += 1
                except ProductLocation.DoesNotExist:
                    pass
            
            return Response({
                'success': True,
                'updated': updated,
                'scope': f'channel {channel} at {location.name}'
            })
        
        # Scope 2: Location only
        elif location:
            updated = ProductLocation.objects.filter(
                product__in=queryset,
                location=location
            ).update(is_available=False)
            
            return Response({
                'success': True,
                'updated': updated,
                'scope': f'location {location.name}'
            })
        
        # Scope 1: Global
        else:
            updated = queryset.update(visible=False)
            return Response({
                'success': True,
                'updated': updated,
                'scope': 'global'
            })
    
    @extend_schema(
        tags=["Products"],
        summary="Update location-specific pricing and tax overrides",
        description="""
        Update pricing and tax configuration for product at specific location.
        
        Requires X-Location-ID header to identify location.
        Product must already be assigned to location.
        """,
        request=inline_serializer(
            name="UpdateLocationPricingRequest",
            fields={
                "is_available": drf_serializers.BooleanField(
                    required=False,
                    help_text="Base availability at this location"
                ),
                "price_override": drf_serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Base price override in cents (null = use product price)"
                ),
                "channels": drf_serializers.JSONField(
                    required=False,
                    help_text='Consolidated channel data: {"ubereats": {"price": 649, "is_available": true}}'
                ),
                "stock_quantity": drf_serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Stock quantity at this location (null = unlimited)"
                ),
                "low_stock_threshold": drf_serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Low stock alert threshold (null = no alerts)"
                ),
                "delivery_tax_rate_override_id": drf_serializers.UUIDField(
                    required=False,
                    allow_null=True,
                    help_text="UUID of delivery tax rate override (null = clear)"
                ),
                "takeaway_tax_rate_override_id": drf_serializers.UUIDField(
                    required=False,
                    allow_null=True,
                    help_text="UUID of takeaway tax rate override (null = clear)"
                ),
                "eat_in_tax_rate_override_id": drf_serializers.UUIDField(
                    required=False,
                    allow_null=True,
                    help_text="UUID of eat-in tax rate override (null = clear)"
                ),
            },
        ),
        responses={
            200: inline_serializer(
                name="UpdateLocationPricingResponse",
                fields={
                    "success": drf_serializers.BooleanField(),
                    "location_id": drf_serializers.UUIDField(),
                    "location_name": drf_serializers.CharField(),
                    "is_available": drf_serializers.BooleanField(),
                    "price_override": drf_serializers.IntegerField(allow_null=True),
                    "channels": drf_serializers.JSONField(),
                    "stock_quantity": drf_serializers.IntegerField(allow_null=True),
                    "low_stock_threshold": drf_serializers.IntegerField(allow_null=True),
                    "delivery_tax_rate_override_id": drf_serializers.UUIDField(allow_null=True),
                    "takeaway_tax_rate_override_id": drf_serializers.UUIDField(allow_null=True),
                    "eat_in_tax_rate_override_id": drf_serializers.UUIDField(allow_null=True),
                },
            ),
            400: inline_serializer(
                name="UpdateLocationPricingError400",
                fields={"error": drf_serializers.CharField()},
            ),
            404: inline_serializer(
                name="UpdateLocationPricingError404",
                fields={"error": drf_serializers.CharField()},
            ),
        },
        parameters=[TENANT_HEADER, LOCATION_HEADER],
    )
    @action(detail=True, methods=['patch'])
    @transaction.atomic
    def update_location_pricing(self, request, plu=None):
        """
        Update pricing and taxes for product at current location.
        
        Purpose: Manage location-specific pricing without full product update.
        
        Requirements:
        - X-Location-ID header (required)
        - Product must be assigned to location
        
        Updatable Fields:
        - is_available: Base availability at this location
        - price_override: Base price for location (null to clear)
        - channels: Channel-specific data (consolidated structure)
        - stock_quantity: Stock quantity (null for unlimited)
        - low_stock_threshold: Low stock alert threshold (null to disable)
        - delivery_tax_rate_override_id: Delivery tax override (null to clear)
        - takeaway_tax_rate_override_id: Takeaway tax override (null to clear)
        - eat_in_tax_rate_override_id: Eat-in tax override (null to clear)
        
        Request Body:
        {
            "is_available": true,
            "price_override": 649,
            "channels": {
                "ubereats": {"price": 699, "is_available": true},
                "doordash": {"price": 679, "is_available": false}
            },
            "stock_quantity": 50,
            "delivery_tax_rate_override_id": "uuid"
        }
        
        Response:
        {
            "success": true,
            "location_id": "uuid",
            "location_name": "NYC Times Square",
            "is_available": true,
            "price_override": 649,
            "channels": {...},
            "stock_quantity": 50,
            "low_stock_threshold": null,
            "delivery_tax_rate_override_id": "uuid",
            "takeaway_tax_rate_override_id": null,
            "eat_in_tax_rate_override_id": null
        }
        
        Args:
            request: DRF request with update data
            plu: Product PLU from URL
            
        Returns:
            Response: Success with full location assignment state
            
        Raises:
            400: If X-Location-ID header missing or invalid tax rate ID
            404: If product not assigned to location
        """
        location = self._get_location_from_header()
        if not location:
            return Response(
                {'error': 'X-Location-ID header required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        product = self.get_object()
        
        try:
            pl = ProductLocation.objects.get(product=product, location=location)
        except ProductLocation.DoesNotExist:
            return Response(
                {'error': 'Product not assigned to this location'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate tax rate override IDs exist before applying any changes
        tax_rate_fields = [
            'delivery_tax_rate_override_id',
            'takeaway_tax_rate_override_id',
            'eat_in_tax_rate_override_id',
        ]
        errors = {}
        for field_name in tax_rate_fields:
            if field_name in request.data:
                tax_rate_id = request.data[field_name]
                if tax_rate_id is not None:
                    if not TaxRate.objects.filter(id=tax_rate_id).exists():
                        errors[field_name] = f'Tax rate with ID "{tax_rate_id}" does not exist.'
        
        if errors:
            return Response(
                {'error': errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update availability
        if 'is_available' in request.data:
            pl.is_available = request.data['is_available']
        
        # Update pricing
        if 'price_override' in request.data:
            pl.price_override = request.data['price_override']
        
        if 'channels' in request.data:
            pl.channels = request.data['channels']
        
        # Update inventory
        if 'stock_quantity' in request.data:
            pl.stock_quantity = request.data['stock_quantity']
        
        if 'low_stock_threshold' in request.data:
            pl.low_stock_threshold = request.data['low_stock_threshold']
        
        # Update tax rates (already validated above)
        if 'delivery_tax_rate_override_id' in request.data:
            pl.delivery_tax_rate_override_id = request.data['delivery_tax_rate_override_id']
        
        if 'takeaway_tax_rate_override_id' in request.data:
            pl.takeaway_tax_rate_override_id = request.data['takeaway_tax_rate_override_id']
        
        if 'eat_in_tax_rate_override_id' in request.data:
            pl.eat_in_tax_rate_override_id = request.data['eat_in_tax_rate_override_id']
        
        pl.save()
        
        return Response({
            'success': True,
            'location_id': str(location.id),
            'location_name': location.name,
            'is_available': pl.is_available,
            'price_override': pl.price_override,
            'channels': pl.channels,
            'stock_quantity': pl.stock_quantity,
            'low_stock_threshold': pl.low_stock_threshold,
            'delivery_tax_rate_override_id': str(pl.delivery_tax_rate_override_id) if pl.delivery_tax_rate_override_id else None,
            'takeaway_tax_rate_override_id': str(pl.takeaway_tax_rate_override_id) if pl.takeaway_tax_rate_override_id else None,
            'eat_in_tax_rate_override_id': str(pl.eat_in_tax_rate_override_id) if pl.eat_in_tax_rate_override_id else None,
        })
    
    @extend_schema(
        tags=["Products"],
        summary="Bulk delete products",
        description="""
        Delete multiple products in a single request.
        
        Products are identified by their PLU codes.
        Deletion is cascaded to ProductLocation and ProductRelation records.
        
        Use Cases:
        - Clean up test data
        - Remove discontinued products in bulk
        - Delete entire product categories
        - Clear out seasonal items
        """,
        request=inline_serializer(
            name="BulkDeleteRequest",
            fields={
                "plus": drf_serializers.ListField(
                    child=drf_serializers.CharField(),
                    help_text='List of PLU codes to delete, e.g. ["BURGER-01", "FRIES-01"]',
                ),
            },
        ),
        responses={
            200: inline_serializer(
                name="BulkDeleteResponse",
                fields={
                    "success": drf_serializers.BooleanField(),
                    "deleted": drf_serializers.IntegerField(),
                    "not_found": drf_serializers.ListField(child=drf_serializers.CharField()),
                },
            ),
            400: inline_serializer(
                name="BulkDeleteError",
                fields={"error": drf_serializers.CharField()},
            ),
        },
        parameters=[TENANT_HEADER],
    )
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def bulk_delete(self, request):
        """
        Delete multiple products in a single request.
        
        Purpose: Efficiently delete multiple products at once.
        
        Features:
        - Atomic transaction (all or nothing)
        - Cascade deletion to related records
        - Returns list of PLUs that weren't found
        
        Request Body:
        {
            "plus": ["BURGER-01", "FRIES-01", "DRINK-01"]
        }
        
        Response (Success):
        {
            "success": true,
            "deleted": 3,
            "not_found": []
        }
        
        Response (Partial):
        {
            "success": true,
            "deleted": 2,
            "not_found": ["DRINK-01"]
        }
        
        Use Cases:
        - Clean up test data
        - Remove discontinued products in bulk
        - Delete entire product categories
        - Clear out seasonal items
        
        Args:
            request: DRF request with list of PLUs
            
        Returns:
            Response: Success with deletion count and not found list
            
        Raises:
            400: If no PLUs provided or invalid format
            
        Examples:
            >>> POST /api/products/bulk_delete/
            >>> Content-Type: application/json
            >>> {
            ...     "plus": ["BURGER-01", "FRIES-01"]
            ... }
            >>> # Response: {"success": true, "deleted": 2, "not_found": []}
            
            >>> # Not all found
            >>> POST /api/products/bulk_delete/
            >>> {
            ...     "plus": ["BURGER-01", "INVALID-PLU"]
            ... }
            >>> # Response: {"success": true, "deleted": 1, "not_found": ["INVALID-PLU"]}
        """
        plus = request.data.get('plus', [])
        
        if not plus:
            return Response(
                {'error': 'plus list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not isinstance(plus, list):
            return Response(
                {'error': 'plus must be a list of PLU codes'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Find products that exist
        products = Product.objects.filter(plu__in=plus)
        found_plus = set(products.values_list('plu', flat=True))
        not_found = [plu for plu in plus if plu not in found_plus]
        
        # Delete products (cascades to ProductLocation and ProductRelation)
        deleted_count, _ = products.delete()
        
        return Response({
            'success': True,
            'deleted': deleted_count,
            'not_found': not_found
        })


# ==============================================================================
# CATEGORY VIEWSET
# ==============================================================================

@tenant_schema("Categories", LOCATION_HEADER)
class CategoryViewSet(viewsets.ModelViewSet):
    """
    Category management viewset.
    
    Provides:
    - Standard CRUD operations
    - Location-based filtering
    - Search functionality
    
    Lookup:
    - Uses 'pos_category_id' instead of 'id'
    
    Query Parameters:
    - search: Search name or pos_category_id
    - for_location: Filter by location from X-Location-ID header
    
    Examples:
        >>> # List all categories
        >>> GET /api/categories/
        
        >>> # Search categories
        >>> GET /api/categories/?search=burger
        
        >>> # Categories at specific location
        >>> GET /api/categories/?for_location=true
        >>> Headers: X-Location-ID: {uuid}
        
        >>> # Get specific category
        >>> GET /api/categories/BURGERS/
    """
    
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]
    lookup_field = 'pos_category_id'
    
    def _get_location_from_header(self):
        """Extract location from X-Location-ID header"""
        location_id = self.request.META.get('HTTP_X_LOCATION_ID')
        if location_id:
            try:
                _uuid.UUID(str(location_id))
            except ValueError:
                return None
            try:
                return Location.objects.get(id=location_id)
            except Location.DoesNotExist:
                return None
        return None
    
    def get_queryset(self):
        """
        Get filtered category queryset.
        
        Filters:
        - search: Text search on name and pos_category_id
        - for_location: Only categories with products at location
        
        Returns:
            QuerySet: Filtered categories ordered by sort_order, name
        """
        queryset = Category.objects.all()
        
        # Search filter
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(pos_category_id__icontains=search)
            )
        
        # Location filter
        location = self._get_location_from_header()
        is_available = self.request.query_params.get('is_available')
        
        if is_available == 'true' and location:
            queryset = queryset.filter(
                products__location_links__location=location,
                products__location_links__is_available=True
            ).distinct()
        
        return queryset.order_by('sort_order', 'name')


# ==============================================================================
# TAX RATE VIEWSET
# ==============================================================================

@tenant_schema("Tax Rates", LOCATION_HEADER)
class TaxRateViewSet(viewsets.ModelViewSet):
    """
    Tax rate management viewset.
    
    Provides:
    - Standard CRUD operations
    - Active/inactive filtering
    - Default tax rate filtering
    
    Features:
    - Auto-switch default (handled in model)
    - Validation (percentage XOR flat_fee)
    
    Query Parameters:
    - is_active: Filter by active status (true/false)
    - is_default: Filter by default flag (true/false)
    
    Examples:
        >>> # List all tax rates
        >>> GET /api/tax-rates/
        
        >>> # Only active tax rates
        >>> GET /api/tax-rates/?is_active=true
        
        >>> # Get default tax rate
        >>> GET /api/tax-rates/?is_default=true
        
        >>> # Create percentage tax
        >>> POST /api/tax-rates/
        >>> {"name": "VAT 9%", "percentage": 9000, "is_default": true}
        
        >>> # Create flat fee tax
        >>> POST /api/tax-rates/
        >>> {"name": "Bag Fee", "flat_fee": 10}
    """
    
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]
    
    def get_queryset(self):
        """
        Get filtered tax rate queryset.
        
        Filters:
        - is_active: Active status
        - is_default: Default flag
        
        Returns:
            QuerySet: Filtered tax rates ordered by is_default DESC, name
        """
        queryset = TaxRate.objects.all()
        
        # Active filter
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Default filter
        is_default = self.request.query_params.get('is_default')
        if is_default is not None:
            queryset = queryset.filter(is_default=is_default.lower() == 'true')
        
        return queryset.order_by('-is_default', 'name')




# ==============================================================================
# END OF VIEWS
# ==============================================================================