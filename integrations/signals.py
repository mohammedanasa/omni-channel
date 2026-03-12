"""
Product mutation signals for outbound channel sync.

When products or product-location assignments change, these signals
queue a menu push to all active channel links for affected locations.

Signals are connected in IntegrationsConfig.ready().
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _sync_location_channels(location, reason=""):
    """Push menu to all active channels for a location (async-safe stub)."""
    from integrations.services import IntegrationSyncService

    logger.info("Outbound sync triggered for location %s: %s", location, reason)
    results = IntegrationSyncService.push_to_active_channels(location)
    for r in results:
        if not r["result"].get("success"):
            logger.warning(
                "Outbound sync to %s failed: %s",
                r["channel"],
                r["result"].get("message"),
            )


@receiver(post_save, sender="products.ProductLocation")
def on_product_location_saved(sender, instance, created, **kwargs):
    """Sync channels when a product is assigned/updated at a location."""
    _sync_location_channels(
        instance.location,
        reason=f"ProductLocation {'created' if created else 'updated'} for {instance.product}",
    )


@receiver(post_delete, sender="products.ProductLocation")
def on_product_location_deleted(sender, instance, **kwargs):
    """Sync channels when a product is removed from a location."""
    _sync_location_channels(
        instance.location,
        reason=f"ProductLocation deleted for {instance.product}",
    )
