from django.contrib import admin
from .models import Order, OrderItem, OrderModifier, OrderStatusLog


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderStatusLogInline(admin.TabularInline):
    model = OrderStatusLog
    extra = 0
    readonly_fields = ["from_status", "to_status", "changed_by", "reason", "timestamp"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number", "status", "order_type", "location",
        "customer_name", "total", "placed_at",
    ]
    list_filter = ["status", "order_type"]
    search_fields = ["order_number", "external_order_id", "customer_name"]
    inlines = [OrderItemInline, OrderStatusLogInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "plu", "name", "quantity", "unit_price", "total_price"]


@admin.register(OrderModifier)
class OrderModifierAdmin(admin.ModelAdmin):
    list_display = ["order_item", "plu", "name", "quantity", "unit_price"]


@admin.register(OrderStatusLog)
class OrderStatusLogAdmin(admin.ModelAdmin):
    list_display = ["order", "from_status", "to_status", "changed_by", "timestamp"]
    readonly_fields = ["order", "from_status", "to_status", "changed_by", "reason", "timestamp"]
