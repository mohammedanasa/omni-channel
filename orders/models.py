from django.db import models
from common.models import BaseUUIDModel


class OrderStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    ACCEPTED = "accepted", "Accepted"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready"
    PICKED_UP = "picked_up", "Picked Up"
    DELIVERED = "delivered", "Delivered"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"


class OrderType(models.TextChoices):
    DELIVERY = "delivery", "Delivery"
    TAKEAWAY = "takeaway", "Takeaway"
    EAT_IN = "eat_in", "Eat In"
    PICKUP = "pickup", "Pickup"


VALID_TRANSITIONS = {
    OrderStatus.RECEIVED: [
        OrderStatus.ACCEPTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    ],
    OrderStatus.ACCEPTED: [
        OrderStatus.PREPARING,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    ],
    OrderStatus.PREPARING: [
        OrderStatus.READY,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    ],
    OrderStatus.READY: [
        OrderStatus.PICKED_UP,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    ],
    OrderStatus.PICKED_UP: [
        OrderStatus.DELIVERED,
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
    ],
    OrderStatus.DELIVERED: [
        OrderStatus.COMPLETED,
    ],
    OrderStatus.COMPLETED: [],
    OrderStatus.REJECTED: [],
    OrderStatus.CANCELLED: [],
    OrderStatus.FAILED: [],
}


class Order(BaseUUIDModel):
    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    external_order_id = models.CharField(max_length=255, blank=True, default="")

    channel = models.ForeignKey(
        "channels.Channel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    channel_link = models.ForeignKey(
        "integrations.ChannelLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    location = models.ForeignKey(
        "locations.Location",
        on_delete=models.CASCADE,
        related_name="orders",
    )

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.RECEIVED,
    )
    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        default=OrderType.DELIVERY,
    )

    # Customer
    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_phone = models.CharField(max_length=50, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")
    delivery_address = models.TextField(blank=True, default="")

    # Financials (all in cents)
    subtotal = models.IntegerField(default=0)
    tax_total = models.IntegerField(default=0)
    delivery_fee = models.IntegerField(default=0)
    service_fee = models.IntegerField(default=0)
    tip = models.IntegerField(default=0)
    discount_total = models.IntegerField(default=0)
    total = models.IntegerField(default=0)

    # Timing
    placed_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    estimated_prep_time = models.IntegerField(
        null=True, blank=True, help_text="Estimated prep time in minutes"
    )
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True, default="")
    raw_payload = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-placed_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "location"]),
            models.Index(fields=["channel", "external_order_id"]),
            models.Index(fields=["-placed_at"]),
        ]

    def __str__(self):
        return f"Order {self.order_number} ({self.status})"


class OrderItem(BaseUUIDModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    plu = models.CharField(max_length=50, help_text="Snapshot of product PLU")
    name = models.CharField(max_length=255, help_text="Snapshot of product name")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.IntegerField(default=0, help_text="Price per unit in cents")
    total_price = models.IntegerField(default=0, help_text="quantity * unit_price in cents")
    tax_amount = models.IntegerField(default=0, help_text="Tax for this line item in cents")
    notes = models.TextField(blank=True, default="")
    sort_order = models.IntegerField(default=0)
    external_item_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.quantity}x {self.name}"


class OrderModifier(BaseUUIDModel):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name="modifiers"
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_modifiers",
    )
    plu = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.IntegerField(default=0)
    total_price = models.IntegerField(default=0)
    group_name = models.CharField(max_length=255, blank=True, default="")
    group_plu = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        ordering = ["group_name", "name"]

    def __str__(self):
        return f"{self.quantity}x {self.name} (mod)"


class OrderStatusLog(BaseUUIDModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_logs")
    from_status = models.CharField(max_length=20, choices=OrderStatus.choices, blank=True, default="")
    to_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    changed_by = models.CharField(max_length=255, blank=True, default="", help_text="User email or system identifier")
    reason = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.order.order_number}: {self.from_status} → {self.to_status}"
