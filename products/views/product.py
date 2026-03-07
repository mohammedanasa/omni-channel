from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db.models import Q, Prefetch

from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
    OpenApiParameter,
)
from rest_framework import serializers as drf_serializers

from ..models import Product, ProductLocation
from ..serializers import (
    ProductSerializer,
    NestedProductSerializer,
    CategorySerializer,
    BulkProductSyncSerializer,
)
from ..services import MenuService, AvailabilityService, PricingService, ProductService
from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema, TENANT_HEADER, LOCATION_HEADER
from .mixins import HeaderContextMixin
from .constants import CHANNEL_HEADER, PRODUCT_TYPE_FILTER


@tenant_schema("Products", LOCATION_HEADER)
class ProductViewSet(HeaderContextMixin, viewsets.ModelViewSet):
    """
    Complete product management viewset with custom actions.

    Lookup: Uses 'plu' field instead of 'id'.
    Headers: X-Location-ID (optional), X-Channel (optional).
    Query Params: product_type, category_id, visible, is_available, is_active, search, expand.
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]
    lookup_field = 'plu'

    # ========== LIST ==========

    @extend_schema(
        tags=["Products"],
        summary="List products",
        description=(
            "Returns a list of products. Supports filtering by product_type, "
            "category_id, visible, for_location, is_active, and text search."
        ),
        parameters=[TENANT_HEADER, LOCATION_HEADER, PRODUCT_TYPE_FILTER],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    # ========== QUERYSET ==========

    def get_queryset(self):
        queryset = Product.objects.select_related(
            'delivery_tax_rate',
            'takeaway_tax_rate',
            'eat_in_tax_rate',
        ).prefetch_related(
            'categories',
            Prefetch(
                'location_links',
                queryset=ProductLocation.objects.select_related(
                    'location',
                    'delivery_tax_rate_override',
                    'takeaway_tax_rate_override',
                    'eat_in_tax_rate_override',
                ),
            ),
        )

        product_type = self.request.query_params.get('product_type')
        if product_type:
            queryset = queryset.filter(product_type=int(product_type))

        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(categories__pos_category_id=category_id)

        visible = self.request.query_params.get('visible')
        if visible is not None:
            queryset = queryset.filter(visible=visible.lower() == 'true')

        location = self._get_location_from_header()
        if location:
            location_filter = {'location_links__location': location}
            is_available_at_location = self.request.query_params.get('is_available')
            if is_available_at_location and is_available_at_location.lower() == 'true':
                location_filter['location_links__is_available'] = True
            queryset = queryset.filter(**location_filter)

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(plu__icontains=search)
                | Q(kitchen_name__icontains=search)
            )

        return queryset.distinct()

    # ========== SERIALIZER SELECTION ==========

    def get_serializer_class(self):
        expand = self.request.query_params.get('expand', '')
        expand_fields = [f.strip() for f in expand.split(',') if f.strip()]
        if 'sub_products' in expand_fields:
            return NestedProductSerializer
        return ProductSerializer

    # ========== CONTEXT ==========

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['location'] = self._get_location_from_header()
        context['channel'] = self._get_channel_from_header()
        expand = self.request.query_params.get('expand', '')
        context['expand'] = [f.strip() for f in expand.split(',') if f.strip()]
        return context

    # ========== CREATE ==========

    def perform_create(self, serializer):
        product = serializer.save()
        location = self._get_location_from_header()
        if location:
            ProductService.auto_assign_location(product, location)
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
    def bulk_sync(self, request):
        serializer = BulkProductSyncSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )

        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = serializer.save()
            return Response({
                'success': True,
                'products_synced': len(result['products']),
                'categories_synced': result['categories_count'],
                'tax_rates_synced': result['tax_rates_count'],
            })
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Products"],
        summary="Export menu for delivery channel",
        description="Export complete menu tree. Requires X-Location-ID header.",
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
                description="Filter by POS category ID",
            ),
            OpenApiParameter(
                name="visible_only",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Only visible products (default: true)",
            ),
        ],
    )
    @action(detail=False, methods=['get'])
    def export_menu(self, request):
        location = self._get_location_from_header()
        if not location:
            return Response(
                {'error': 'X-Location-ID header required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = MenuService.export_menu(
            location=location,
            channel=self._get_channel_from_header(),
            category_id=request.query_params.get('category_id'),
            visible_only=request.query_params.get('visible_only', 'true').lower() == 'true',
        )

        serializer = NestedProductSerializer(
            result['products'],
            many=True,
            context={**self.get_serializer_context(), 'max_depth': 10},
        )

        return Response({
            'products': serializer.data,
            'categories': CategorySerializer(result['categories'], many=True).data,
            'metadata': result['metadata'],
        })

    @extend_schema(
        tags=["Products"],
        summary="Mark products unavailable",
        description=(
            "Mark products as unavailable globally, per location, or per channel.\n\n"
            "Scope depends on headers:\n"
            "- No headers: Global (product.visible = false)\n"
            "- X-Location-ID only: Location-wide\n"
            "- X-Location-ID + X-Channel: Channel-specific"
        ),
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
    def mark_unavailable(self, request):
        plus = request.data.get('plus', [])
        tags = request.data.get('tags', [])

        if not plus and not tags:
            return Response(
                {'error': 'Either plus or tags required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = AvailabilityService.mark_unavailable(
            plus=plus,
            tags=tags,
            location=self._get_location_from_header(),
            channel=self._get_channel_from_header(),
        )

        return Response({'success': True, **result})

    @extend_schema(
        tags=["Products"],
        summary="Update location-specific pricing and tax overrides",
        description=(
            "Update pricing and tax configuration for product at specific location.\n"
            "Requires X-Location-ID header. Product must already be assigned to location."
        ),
        request=inline_serializer(
            name="UpdateLocationPricingRequest",
            fields={
                "is_available": drf_serializers.BooleanField(
                    required=False,
                    help_text="Base availability at this location",
                ),
                "price_override": drf_serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Base price override in cents (null = use product price)",
                ),
                "channels": drf_serializers.JSONField(
                    required=False,
                    help_text='Consolidated channel data: {"ubereats": {"price": 649, "is_available": true}}',
                ),
                "stock_quantity": drf_serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Stock quantity at this location (null = unlimited)",
                ),
                "low_stock_threshold": drf_serializers.IntegerField(
                    required=False,
                    allow_null=True,
                    help_text="Low stock alert threshold (null = no alerts)",
                ),
                "delivery_tax_rate_override_id": drf_serializers.UUIDField(
                    required=False,
                    allow_null=True,
                    help_text="UUID of delivery tax rate override (null = clear)",
                ),
                "takeaway_tax_rate_override_id": drf_serializers.UUIDField(
                    required=False,
                    allow_null=True,
                    help_text="UUID of takeaway tax rate override (null = clear)",
                ),
                "eat_in_tax_rate_override_id": drf_serializers.UUIDField(
                    required=False,
                    allow_null=True,
                    help_text="UUID of eat-in tax rate override (null = clear)",
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
    def update_location_pricing(self, request, plu=None):
        location = self._get_location_from_header()
        if not location:
            return Response(
                {'error': 'X-Location-ID header required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = self.get_object()

        try:
            result = PricingService.update_location_pricing(product, location, request.data)
            return Response({'success': True, **result})
        except ProductLocation.DoesNotExist:
            return Response(
                {'error': 'Product not assigned to this location'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as e:
            return Response(
                {'error': e.message_dict if hasattr(e, 'message_dict') else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        tags=["Products"],
        summary="Bulk delete products",
        description="Delete multiple products by PLU codes. Cascades to related records.",
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
    def bulk_delete(self, request):
        plus = request.data.get('plus', [])

        if not plus:
            return Response(
                {'error': 'plus list is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(plus, list):
            return Response(
                {'error': 'plus must be a list of PLU codes'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = ProductService.bulk_delete(plus)
        return Response({'success': True, **result})
