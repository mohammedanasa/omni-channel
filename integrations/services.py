import logging

from django.db import transaction
from django.utils import timezone

from common.constants import INTERNAL_POS_SLUG
from integrations.adapters import AdapterRegistry
from integrations.canonical.menu import CanonicalMenu
from integrations.canonical.results import SyncResult
from integrations.models import ChannelLink, SyncStatus

logger = logging.getLogger(__name__)


class IntegrationSyncService:
    """Orchestrates sync operations between external channels and the local DB."""

    @staticmethod
    @transaction.atomic
    def pull_and_persist(channel_link: ChannelLink) -> SyncResult:
        """
        Pull menu from an external channel and upsert into local products.

        Flow:
        1. adapter.pull_menu() → CanonicalMenu
        2. Convert CanonicalMenu → bulk_sync payload
        3. Upsert tax rates, categories, products
        4. Map external IDs via ProductChannelConfig

        Returns SyncResult with counts.
        """
        from products.models import Product, Category, TaxRate, ProductLocation

        adapter = AdapterRegistry.get_adapter(channel_link)

        channel_link.sync_status = SyncStatus.SYNCING
        channel_link.save(update_fields=["sync_status"])

        try:
            canonical_menu = adapter.pull_menu()
        except Exception as e:
            channel_link.sync_status = SyncStatus.ERROR
            channel_link.sync_error = str(e)
            channel_link.save(update_fields=["sync_status", "sync_error"])
            return SyncResult(success=False, message=f"Pull failed: {e}", errors=[str(e)])

        created_count = 0
        updated_count = 0
        errors = []

        # 1. Upsert categories
        category_map = {}
        for cat_name in canonical_menu.categories:
            cat, was_created = Category.objects.update_or_create(
                pos_category_id=cat_name.lower().replace(" ", "-"),
                defaults={"name": cat_name},
            )
            category_map[cat_name] = cat

        # Determine ownership: POS channels own catalog, marketplaces seed as local
        is_pos_channel = channel_link.channel.channel_type == "pos"
        channel_slug = channel_link.channel.slug
        ownership_slug = channel_slug if is_pos_channel else INTERNAL_POS_SLUG

        # 2. Upsert products
        for cp in canonical_menu.products:
            try:
                existing = Product.objects.filter(plu=cp.plu).first()

                defaults = {
                    "name": cp.name,
                    "description": cp.description,
                    "image_url": cp.image_url,
                    "price": cp.price,
                    "sort_order": cp.sort_order,
                    "visible": cp.is_available,
                }

                if existing:
                    # Never downgrade from external POS to internal_pos
                    existing_owner = existing.managed_by
                    if _should_update_ownership(existing_owner, ownership_slug):
                        defaults["managed_by"] = ownership_slug

                    for field, value in defaults.items():
                        setattr(existing, field, value)
                    existing.save()
                    product = existing
                    updated_count += 1
                else:
                    defaults["managed_by"] = ownership_slug
                    product = Product.objects.create(plu=cp.plu, **defaults)
                    created_count += 1

                # Assign category
                if cp.category_name and cp.category_name in category_map:
                    product.categories.add(category_map[cp.category_name])

                # Assign to location with channel-specific pricing
                pl, _ = ProductLocation.objects.get_or_create(
                    product=product,
                    location=channel_link.location,
                    defaults={"is_available": cp.is_available},
                )
                pl.is_available = cp.is_available
                # Store channel-specific price
                pl.set_channel_data(
                    channel_link.channel.slug,
                    price=cp.price,
                    is_available=cp.is_available,
                )
                pl.save()

                # Track external ID mapping
                if cp.external_id:
                    from integrations.models import ProductChannelConfig

                    ProductChannelConfig.objects.update_or_create(
                        product_location=pl,
                        channel=channel_link.channel,
                        defaults={
                            "external_product_id": cp.external_id,
                            "price": cp.price,
                            "is_available": cp.is_available,
                        },
                    )

                # Process modifier groups → create sub-products
                for mg in cp.modifier_groups:
                    group_defaults = {
                        "name": mg.name,
                        "product_type": Product.ProductType.MODIFIER_GROUP,
                        "min_select": mg.min_select,
                        "max_select": mg.max_select,
                        "sort_order": mg.sort_order,
                    }
                    existing_group = Product.objects.filter(plu=mg.plu).first()
                    if existing_group:
                        if _should_update_ownership(existing_group.managed_by, ownership_slug):
                            group_defaults["managed_by"] = ownership_slug
                        for field, value in group_defaults.items():
                            setattr(existing_group, field, value)
                        existing_group.save()
                        group = existing_group
                    else:
                        group_defaults["managed_by"] = ownership_slug
                        group = Product.objects.create(plu=mg.plu, **group_defaults)

                    # Link group to parent product
                    from products.models import ProductRelation

                    ProductRelation.objects.get_or_create(
                        parent=product,
                        child=group,
                        defaults={"sort_order": mg.sort_order},
                    )

                    for mod in mg.modifiers:
                        mod_defaults = {
                            "name": mod.name,
                            "product_type": Product.ProductType.MODIFIER_ITEM,
                            "price": mod.price,
                            "sort_order": mod.sort_order,
                        }
                        existing_mod = Product.objects.filter(plu=mod.plu).first()
                        if existing_mod:
                            if _should_update_ownership(existing_mod.managed_by, ownership_slug):
                                mod_defaults["managed_by"] = ownership_slug
                            for field, value in mod_defaults.items():
                                setattr(existing_mod, field, value)
                            existing_mod.save()
                            modifier = existing_mod
                        else:
                            mod_defaults["managed_by"] = ownership_slug
                            modifier = Product.objects.create(plu=mod.plu, **mod_defaults)
                        ProductRelation.objects.get_or_create(
                            parent=group,
                            child=modifier,
                            defaults={"sort_order": mod.sort_order},
                        )

                        # Assign modifier to same location
                        mod_pl, _ = ProductLocation.objects.get_or_create(
                            product=modifier,
                            location=channel_link.location,
                            defaults={"is_available": mod.is_available},
                        )
                        mod_pl.is_available = mod.is_available
                        mod_pl.set_channel_data(
                            channel_link.channel.slug,
                            price=mod.price,
                            is_available=mod.is_available,
                        )
                        mod_pl.save()

            except Exception as e:
                logger.error("Failed to sync product %s: %s", cp.plu, e)
                errors.append(f"{cp.plu}: {e}")

        # Update sync status
        channel_link.sync_status = SyncStatus.SYNCED if not errors else SyncStatus.ERROR
        channel_link.sync_error = "; ".join(errors) if errors else ""
        channel_link.last_sync_at = timezone.now()
        channel_link.save(update_fields=["sync_status", "sync_error", "last_sync_at"])

        return SyncResult(
            success=len(errors) == 0,
            message=f"Pulled {created_count + updated_count} products ({created_count} created, {updated_count} updated).",
            created_count=created_count,
            updated_count=updated_count,
            errors=errors,
        )

    @staticmethod
    def push_to_active_channels(location, exclude_channel_slug=None):
        """
        Push menu to all active non-POS channel links for a location.

        Called after product mutations to keep marketplace channels in sync.
        Skips all POS-type channels (catalog push to POS reverses the
        intended data flow) and optionally excludes a specific channel
        (e.g., the one that triggered the change via webhook).
        """
        links = ChannelLink.objects.filter(
            location=location,
            is_active=True,
        ).select_related("channel")

        results = []
        for link in links:
            if link.channel.channel_type == "pos":
                continue
            if exclude_channel_slug and link.channel.slug == exclude_channel_slug:
                continue

            try:
                adapter = AdapterRegistry.get_adapter(link)
                qs = _get_products_for_location(link.location)
                menu = CanonicalMenu.from_product_queryset(
                    qs, link.location, channel_slug=link.channel.slug
                )
                result = adapter.push_menu(menu)

                link.sync_status = SyncStatus.SYNCED if result.success else SyncStatus.ERROR
                link.sync_error = "" if result.success else result.message
                link.last_sync_at = timezone.now()
                link.save(update_fields=["sync_status", "sync_error", "last_sync_at"])

                results.append({"channel": link.channel.slug, "result": result.to_dict()})
            except Exception as e:
                logger.error("Push to %s failed: %s", link.channel.slug, e)
                link.sync_status = SyncStatus.ERROR
                link.sync_error = str(e)
                link.save(update_fields=["sync_status", "sync_error"])
                results.append(
                    {"channel": link.channel.slug, "result": {"success": False, "message": str(e)}}
                )

        return results


def _get_products_for_location(location):
    from products.models import Product

    return Product.objects.filter(locations__location=location).distinct()


def _should_update_ownership(current_owner: str, new_owner: str) -> bool:
    """
    Determine whether managed_by should be updated.

    Precedence: external POS (clover, square, ...) > internal_pos > ""
    Never downgrade from an external POS slug to internal_pos or empty.
    """
    # If new owner is the same, no-op
    if current_owner == new_owner:
        return False

    # External POS always wins — allow upgrade to external POS
    if new_owner not in ("", INTERNAL_POS_SLUG):
        return True

    # New owner is internal_pos or empty — only allow if current is also internal/empty
    return current_owner in ("", INTERNAL_POS_SLUG)
