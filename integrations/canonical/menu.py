from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanonicalModifier:
    plu: str
    name: str
    price: int  # cents
    is_available: bool = True
    external_id: str = ""
    sort_order: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class CanonicalModifierGroup:
    plu: str
    name: str
    min_select: int = 0
    max_select: int = 0
    modifiers: list[CanonicalModifier] = field(default_factory=list)
    sort_order: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class CanonicalProduct:
    plu: str
    name: str
    description: str = ""
    price: int = 0  # cents
    image_url: str = ""
    is_available: bool = True
    category_name: str = ""
    modifier_groups: list[CanonicalModifierGroup] = field(default_factory=list)
    tax_rate_percentage: Optional[int] = None
    external_id: str = ""
    sort_order: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class CanonicalMenu:
    location_id: str
    location_name: str
    channel_slug: str
    products: list[CanonicalProduct] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_product_queryset(cls, queryset, location, channel_slug: str = "internal_pos") -> CanonicalMenu:
        """Build a CanonicalMenu from a Product queryset for a given location."""
        from products.models import ProductType

        products = []
        category_names = set()

        for product in queryset.select_related("category", "delivery_tax_rate"):
            if product.product_type != ProductType.MAIN:
                continue

            cat_name = product.category.name if product.category else ""
            if cat_name:
                category_names.add(cat_name)

            # Get location-specific pricing
            pl = product.locations.filter(location=location).first()
            price = pl.price if pl else (product.price or 0)
            is_available = pl.is_available if pl else True

            tax_pct = None
            if product.delivery_tax_rate and product.delivery_tax_rate.percentage is not None:
                tax_pct = product.delivery_tax_rate.percentage

            # Build modifier groups from product relations
            modifier_groups = []
            for relation in product.children.filter(
                child__product_type=ProductType.MODIFIER_GROUP
            ).select_related("child").order_by("sort_order"):
                group = relation.child
                modifiers = []
                for mod_rel in group.children.filter(
                    child__product_type=ProductType.MODIFIER_ITEM
                ).select_related("child").order_by("sort_order"):
                    mod = mod_rel.child
                    mod_pl = mod.locations.filter(location=location).first()
                    modifiers.append(CanonicalModifier(
                        plu=mod.plu,
                        name=mod.name,
                        price=mod_pl.price if mod_pl else (mod.price or 0),
                        is_available=mod_pl.is_available if mod_pl else True,
                        sort_order=mod_rel.sort_order,
                    ))
                modifier_groups.append(CanonicalModifierGroup(
                    plu=group.plu,
                    name=group.name,
                    min_select=group.min_select or 0,
                    max_select=group.max_select or 0,
                    modifiers=modifiers,
                    sort_order=relation.sort_order,
                ))

            products.append(CanonicalProduct(
                plu=product.plu,
                name=product.name,
                description=product.description or "",
                price=price,
                image_url=product.image_url or "",
                is_available=is_available,
                category_name=cat_name,
                modifier_groups=modifier_groups,
                tax_rate_percentage=tax_pct,
                sort_order=product.sort_order or 0,
            ))

        return cls(
            location_id=str(location.id),
            location_name=location.name,
            channel_slug=channel_slug,
            products=products,
            categories=sorted(category_names),
        )
