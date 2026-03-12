from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema, LOCATION_HEADER, CHANNEL_LINK_HEADER
from products.views.mixins import HeaderContextMixin

from menus.models import (
    Menu,
    MenuCategory,
    MenuItem,
    MenuAvailability,
    MenuLocation,
    MenuLocationChannel,
)
from menus.serializers import (
    MenuSerializer,
    MenuCategorySerializer,
    MenuItemSerializer,
    MenuAvailabilitySerializer,
    MenuLocationSerializer,
    MenuLocationChannelSerializer,
)
from menus.services import MenuBuilderService, MenuPublisherService


@tenant_schema("Menus", LOCATION_HEADER, CHANNEL_LINK_HEADER)
class MenuViewSet(HeaderContextMixin, viewsets.ModelViewSet):
    serializer_class = MenuSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]

    def get_queryset(self):
        return Menu.objects.prefetch_related(
            "categories__items__product",
            "availabilities",
            "menu_locations__location",
            "menu_locations__channel_publishes__channel_link__channel",
        ).all()

    # ── Categories ──────────────────────────────────────────────

    @extend_schema(
        tags=["Menus"],
        request=MenuCategorySerializer,
        responses=MenuCategorySerializer,
    )
    @action(detail=True, methods=["post"], url_path="categories")
    def categories(self, request, pk=None):
        menu = self.get_object()
        serializer = MenuCategorySerializer(data={**request.data, "menu": menu.id})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Menus"],
        request=MenuCategorySerializer,
        responses=MenuCategorySerializer,
        parameters=[OpenApiParameter("cat_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    )
    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path="categories/(?P<cat_id>[^/.]+)",
    )
    def category_detail(self, request, pk=None, cat_id=None):
        menu = self.get_object()
        try:
            cat = menu.categories.get(id=cat_id)
        except MenuCategory.DoesNotExist:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "DELETE":
            cat.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = MenuCategorySerializer(cat, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    # ── Items ───────────────────────────────────────────────────

    @extend_schema(
        tags=["Menus"],
        request=MenuItemSerializer,
        responses=MenuItemSerializer,
    )
    @action(detail=True, methods=["post"], url_path="items")
    def items(self, request, pk=None):
        menu = self.get_object()
        serializer = MenuItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["menu_category"].menu_id != menu.id:
            return Response(
                {"error": "menu_category does not belong to this menu."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Menus"],
        request=MenuItemSerializer,
        responses=MenuItemSerializer,
        parameters=[OpenApiParameter("item_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    )
    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path="items/(?P<item_id>[^/.]+)",
    )
    def item_detail(self, request, pk=None, item_id=None):
        menu = self.get_object()
        try:
            item = MenuItem.objects.get(id=item_id, menu_category__menu=menu)
        except MenuItem.DoesNotExist:
            return Response({"error": "Item not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "DELETE":
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = MenuItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    # ── Bulk operations ─────────────────────────────────────────

    @extend_schema(tags=["Menus"], request=None, responses={200: dict})
    @action(detail=True, methods=["patch"], url_path="items/bulk")
    def bulk_update_items(self, request, pk=None):
        menu = self.get_object()
        items = request.data.get("items", [])
        if not items or not isinstance(items, list):
            return Response(
                {"error": "'items' must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for entry in items:
            if "id" not in entry:
                return Response(
                    {"error": "Each item must have an 'id'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            updated = MenuBuilderService.bulk_update_items(menu, items)
            return Response({"updated": len(updated)})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(tags=["Menus"], request=None, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="items/bulk-remove")
    def bulk_remove_items(self, request, pk=None):
        menu = self.get_object()
        item_ids = request.data.get("item_ids", [])
        if not item_ids or not isinstance(item_ids, list):
            return Response(
                {"error": "'item_ids' must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted = MenuBuilderService.bulk_remove_items(menu, item_ids)
        return Response({"deleted": deleted})

    @extend_schema(tags=["Menus"], request=None, responses={200: dict})
    @action(detail=True, methods=["patch"], url_path="categories/bulk")
    def bulk_update_categories(self, request, pk=None):
        menu = self.get_object()
        categories = request.data.get("categories", [])
        if not categories or not isinstance(categories, list):
            return Response(
                {"error": "'categories' must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for entry in categories:
            if "id" not in entry:
                return Response(
                    {"error": "Each category must have an 'id'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            updated = MenuBuilderService.bulk_update_categories(menu, categories)
            return Response({"updated": len(updated)})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # ── Availability ────────────────────────────────────────────

    @extend_schema(
        tags=["Menus"],
        request=MenuAvailabilitySerializer,
        responses=MenuAvailabilitySerializer,
    )
    @action(detail=True, methods=["post"], url_path="availabilities")
    def availabilities(self, request, pk=None):
        menu = self.get_object()
        serializer = MenuAvailabilitySerializer(data={**request.data, "menu": menu.id})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Menus"],
        parameters=[OpenApiParameter("avail_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path="availabilities/(?P<avail_id>[^/.]+)",
    )
    def availability_detail(self, request, pk=None, avail_id=None):
        menu = self.get_object()
        try:
            avail = menu.availabilities.get(id=avail_id)
        except MenuAvailability.DoesNotExist:
            return Response({"error": "Availability not found."}, status=status.HTTP_404_NOT_FOUND)
        avail.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Locations ───────────────────────────────────────────────

    @extend_schema(
        tags=["Menus"],
        request=None,
        responses=MenuLocationSerializer,
        parameters=[LOCATION_HEADER],
    )
    @action(detail=True, methods=["post", "delete"], url_path="locations")
    def locations(self, request, pk=None):
        menu = self.get_object()

        location = self._get_location_from_header()
        if not location:
            return Response(
                {"error": "X-Location-ID header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.method == "POST":
            serializer = MenuLocationSerializer(
                data={"menu": menu.id, "location": location.id}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # DELETE
        try:
            ml = menu.menu_locations.get(location=location)
        except MenuLocation.DoesNotExist:
            return Response(
                {"error": "Menu is not assigned to this location."},
                status=status.HTTP_404_NOT_FOUND,
            )
        ml.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Channels ────────────────────────────────────────────────

    @extend_schema(
        tags=["Menus"],
        request=None,
        responses=MenuLocationChannelSerializer,
        parameters=[LOCATION_HEADER, CHANNEL_LINK_HEADER],
    )
    @action(detail=True, methods=["post", "delete"], url_path="channels")
    def channels(self, request, pk=None):
        menu = self.get_object()

        location = self._get_location_from_header()
        if not location:
            return Response(
                {"error": "X-Location-ID header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ml = menu.menu_locations.get(location=location)
        except MenuLocation.DoesNotExist:
            return Response(
                {"error": "Menu is not assigned to this location."},
                status=status.HTTP_404_NOT_FOUND,
            )

        channel_link = self._get_channel_link_from_header()
        if not channel_link:
            return Response(
                {"error": "X-Channel-Link-ID header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.method == "POST":
            serializer = MenuLocationChannelSerializer(
                data={"menu_location": ml.id, "channel_link": channel_link.id}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # DELETE
        try:
            mlc = ml.channel_publishes.get(channel_link=channel_link)
        except MenuLocationChannel.DoesNotExist:
            return Response(
                {"error": "Channel is not assigned to this menu-location."},
                status=status.HTTP_404_NOT_FOUND,
            )
        mlc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Publishing ──────────────────────────────────────────────

    @extend_schema(tags=["Menus"], request=None, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        menu = self.get_object()
        if not menu.is_active:
            return Response(
                {"error": "Cannot publish an inactive menu."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = MenuPublisherService.publish_menu(menu, user=request.user)
        summary = []
        for mlc in results:
            summary.append({
                "location": mlc.menu_location.location.name,
                "channel": mlc.channel_link.channel.display_name,
                "status": mlc.status,
                "error": mlc.error_message or None,
                "snapshot": mlc.snapshot,
            })

        return Response({"published": len(results), "results": summary})

    @extend_schema(tags=["Menus"], responses=MenuLocationChannelSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="publish-status")
    def publish_status(self, request, pk=None):
        menu = self.get_object()
        mlcs = MenuLocationChannel.objects.filter(
            menu_location__menu=menu
        ).select_related(
            "menu_location__location",
            "channel_link__channel",
        )
        return Response(MenuLocationChannelSerializer(mlcs, many=True).data)

    # ── Duplicate ───────────────────────────────────────────────

    @extend_schema(tags=["Menus"], request=None, responses=MenuSerializer)
    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, pk=None):
        menu = self.get_object()
        new_name = request.data.get("name")
        new_menu = MenuBuilderService.duplicate_menu(menu, new_name=new_name)
        return Response(MenuSerializer(new_menu).data, status=status.HTTP_201_CREATED)
