from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from orders.models import (
    Order,
    OrderItem,
    OrderModifier,
    OrderStatus,
    OrderStatusLog,
    VALID_TRANSITIONS,
)

if TYPE_CHECKING:
    from channels.models import Channel
    from integrations.canonical.orders import CanonicalOrder
    from integrations.models import ChannelLink
    from locations.models import Location


class OrderService:

    @staticmethod
    def _generate_order_number() -> str:
        return f"ORD-{uuid.uuid4().hex[:8].upper()}"

    @classmethod
    @transaction.atomic
    def create_order_from_canonical(
        cls,
        canonical_order: CanonicalOrder,
        location: Location,
        channel: Optional[Channel] = None,
        channel_link: Optional[ChannelLink] = None,
    ) -> Order:
        order_kwargs = canonical_order.to_order_kwargs()
        order = Order.objects.create(
            order_number=cls._generate_order_number(),
            location=location,
            channel=channel,
            channel_link=channel_link,
            **order_kwargs,
        )

        # Create items & modifiers
        for idx, canonical_item in enumerate(canonical_order.items):
            from products.models import Product

            product = Product.objects.filter(plu=canonical_item.plu).first()
            item = OrderItem.objects.create(
                order=order,
                product=product,
                plu=canonical_item.plu,
                name=canonical_item.name,
                quantity=canonical_item.quantity,
                unit_price=canonical_item.unit_price,
                total_price=canonical_item.total_price,
                notes=canonical_item.notes,
                sort_order=idx,
                external_item_id=canonical_item.external_item_id,
            )

            for canonical_mod in canonical_item.modifiers:
                mod_product = Product.objects.filter(plu=canonical_mod.plu).first()
                OrderModifier.objects.create(
                    order_item=item,
                    product=mod_product,
                    plu=canonical_mod.plu,
                    name=canonical_mod.name,
                    quantity=canonical_mod.quantity,
                    unit_price=canonical_mod.unit_price,
                    total_price=canonical_mod.unit_price * canonical_mod.quantity,
                    group_name=canonical_mod.group_name,
                    group_plu=canonical_mod.group_plu,
                )

        # Initial status log
        OrderStatusLog.objects.create(
            order=order,
            from_status="",
            to_status=OrderStatus.RECEIVED,
            changed_by="system",
            reason="Order created",
        )

        return order

    @staticmethod
    @transaction.atomic
    def transition_status(
        order: Order,
        new_status: str,
        changed_by: str = "system",
        reason: str = "",
    ) -> Order:
        current = order.status
        allowed = VALID_TRANSITIONS.get(current, [])

        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition from '{current}' to '{new_status}'. "
                f"Valid transitions: {[s.value if hasattr(s, 'value') else s for s in allowed]}"
            )

        old_status = order.status
        order.status = new_status

        # Set timestamp fields
        now = timezone.now()
        timestamp_map = {
            OrderStatus.ACCEPTED: "accepted_at",
            OrderStatus.READY: "ready_at",
            OrderStatus.PICKED_UP: "picked_up_at",
            OrderStatus.DELIVERED: "delivered_at",
        }
        ts_field = timestamp_map.get(new_status)
        if ts_field:
            setattr(order, ts_field, now)

        order.save()

        OrderStatusLog.objects.create(
            order=order,
            from_status=old_status,
            to_status=new_status,
            changed_by=changed_by,
            reason=reason,
        )

        return order
