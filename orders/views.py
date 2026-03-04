from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema
from .models import Order
from .serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    OrderCreateSerializer,
    OrderStatusUpdateSerializer,
)
from .services import OrderService


@tenant_schema("Orders")
class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantAccess]

    def get_queryset(self):
        qs = Order.objects.select_related("channel", "channel_link", "location")
        location_id = self.request.headers.get("X-Location-ID")
        if location_id:
            qs = qs.filter(location_id=location_id)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return OrderListSerializer
        if self.action == "create":
            return OrderCreateSerializer
        return OrderDetailSerializer

    def perform_create(self, serializer):
        from orders.models import OrderStatus, OrderStatusLog

        order = serializer.save(
            order_number=OrderService._generate_order_number(),
        )
        OrderStatusLog.objects.create(
            order=order,
            from_status="",
            to_status=OrderStatus.RECEIVED,
            changed_by=self.request.user.email,
            reason="Order created via API",
        )

    @action(detail=True, methods=["patch"], url_path="status")
    def update_status(self, request, pk=None):
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = OrderService.transition_status(
            order=order,
            new_status=serializer.validated_data["status"],
            changed_by=request.user.email,
            reason=serializer.validated_data.get("reason", ""),
        )

        return Response(OrderDetailSerializer(order).data, status=status.HTTP_200_OK)
