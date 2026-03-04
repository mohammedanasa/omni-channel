from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CanonicalOrderModifier:
    plu: str
    name: str
    quantity: int = 1
    unit_price: int = 0  # cents
    group_name: str = ""
    group_plu: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class CanonicalOrderItem:
    plu: str
    name: str
    quantity: int = 1
    unit_price: int = 0  # cents
    notes: str = ""
    modifiers: list[CanonicalOrderModifier] = field(default_factory=list)
    external_item_id: str = ""

    @property
    def total_price(self) -> int:
        item_total = self.unit_price * self.quantity
        mod_total = sum(m.unit_price * m.quantity for m in self.modifiers)
        return item_total + mod_total

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["total_price"] = self.total_price
        return d


@dataclass
class CanonicalOrder:
    external_order_id: str
    order_type: str  # delivery, takeaway, eat_in, pickup
    items: list[CanonicalOrderItem] = field(default_factory=list)

    # Customer info
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""

    # Delivery
    delivery_address: str = ""

    # Financials (cents)
    subtotal: int = 0
    tax_total: int = 0
    delivery_fee: int = 0
    service_fee: int = 0
    tip: int = 0
    discount_total: int = 0
    total: int = 0

    # Timing
    placed_at: Optional[str] = None  # ISO 8601 string
    estimated_prep_time: Optional[int] = None  # minutes
    estimated_delivery_time: Optional[str] = None  # ISO 8601

    notes: str = ""
    raw_payload: Optional[dict] = None

    @classmethod
    def from_dict(cls, data: dict) -> CanonicalOrder:
        items = []
        for item_data in data.get("items", []):
            modifiers = [
                CanonicalOrderModifier(**m) for m in item_data.pop("modifiers", [])
            ]
            items.append(CanonicalOrderItem(**item_data, modifiers=modifiers))

        return cls(
            external_order_id=data.get("external_order_id", ""),
            order_type=data.get("order_type", "delivery"),
            items=items,
            customer_name=data.get("customer_name", ""),
            customer_phone=data.get("customer_phone", ""),
            customer_email=data.get("customer_email", ""),
            delivery_address=data.get("delivery_address", ""),
            subtotal=data.get("subtotal", 0),
            tax_total=data.get("tax_total", 0),
            delivery_fee=data.get("delivery_fee", 0),
            service_fee=data.get("service_fee", 0),
            tip=data.get("tip", 0),
            discount_total=data.get("discount_total", 0),
            total=data.get("total", 0),
            placed_at=data.get("placed_at"),
            estimated_prep_time=data.get("estimated_prep_time"),
            estimated_delivery_time=data.get("estimated_delivery_time"),
            notes=data.get("notes", ""),
            raw_payload=data.get("raw_payload"),
        )

    def to_order_kwargs(self) -> dict:
        """Convert to kwargs suitable for Order.objects.create()."""
        return {
            "external_order_id": self.external_order_id,
            "order_type": self.order_type,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_email": self.customer_email,
            "delivery_address": self.delivery_address,
            "subtotal": self.subtotal,
            "tax_total": self.tax_total,
            "delivery_fee": self.delivery_fee,
            "service_fee": self.service_fee,
            "tip": self.tip,
            "discount_total": self.discount_total,
            "total": self.total,
            "placed_at": self.placed_at,
            "estimated_prep_time": self.estimated_prep_time,
            "estimated_delivery_time": self.estimated_delivery_time,
            "notes": self.notes,
            "raw_payload": self.raw_payload,
        }

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["items"] = [item.to_dict() for item in self.items]
        return d
