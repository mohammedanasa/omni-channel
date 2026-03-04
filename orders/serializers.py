from rest_framework import serializers
from .models import Order, OrderItem, OrderModifier, OrderStatusLog


class OrderModifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderModifier
        fields = [
            "id", "plu", "name", "quantity", "unit_price",
            "total_price", "group_name", "group_plu",
        ]
        read_only_fields = ["id", "total_price"]


class OrderItemSerializer(serializers.ModelSerializer):
    modifiers = OrderModifierSerializer(many=True, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id", "plu", "name", "quantity", "unit_price",
            "total_price", "tax_amount", "notes", "sort_order",
            "external_item_id", "modifiers",
        ]
        read_only_fields = ["id", "total_price"]


class OrderStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusLog
        fields = ["id", "from_status", "to_status", "changed_by", "reason", "timestamp"]
        read_only_fields = ["id", "timestamp"]


class OrderListSerializer(serializers.ModelSerializer):
    channel_slug = serializers.SlugRelatedField(
        source="channel", slug_field="slug", read_only=True
    )
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "external_order_id", "channel_slug",
            "location", "location_name", "status", "order_type",
            "customer_name", "total", "placed_at", "created_at",
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_logs = OrderStatusLogSerializer(many=True, read_only=True)
    channel_slug = serializers.SlugRelatedField(
        source="channel", slug_field="slug", read_only=True
    )
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "external_order_id",
            "channel", "channel_slug", "channel_link",
            "location", "location_name",
            "status", "order_type",
            "customer_name", "customer_phone", "customer_email",
            "delivery_address",
            "subtotal", "tax_total", "delivery_fee", "service_fee",
            "tip", "discount_total", "total",
            "placed_at", "accepted_at", "ready_at", "picked_up_at",
            "delivered_at", "estimated_prep_time", "estimated_delivery_time",
            "notes", "raw_payload",
            "created_at", "updated_at",
            "items", "status_logs",
        ]
        read_only_fields = [
            "id", "order_number", "created_at", "updated_at",
            "accepted_at", "ready_at", "picked_up_at", "delivered_at",
        ]


class OrderCreateSerializer(serializers.ModelSerializer):
    """Flat serializer for creating orders via the API (items added via service layer)."""

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "external_order_id",
            "channel", "channel_link", "location",
            "order_type",
            "customer_name", "customer_phone", "customer_email",
            "delivery_address",
            "subtotal", "tax_total", "delivery_fee", "service_fee",
            "tip", "discount_total", "total",
            "placed_at", "estimated_prep_time", "estimated_delivery_time",
            "notes", "raw_payload",
        ]
        read_only_fields = ["id", "order_number"]


class OrderStatusUpdateSerializer(serializers.Serializer):
    from .models import OrderStatus
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    reason = serializers.CharField(required=False, default="")
