from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from integrations.models import ChannelLink
    from integrations.canonical.menu import CanonicalMenu
    from integrations.canonical.orders import CanonicalOrder
    from integrations.canonical.results import SyncResult, WebhookResult


class AbstractChannelAdapter(ABC):
    """Base class that every channel adapter must implement."""

    def __init__(self, channel_link: ChannelLink) -> None:
        self.channel_link = channel_link
        self.credentials = channel_link.credentials
        self.location = channel_link.location

    # ── Menu sync ──────────────────────────────────────────────

    @abstractmethod
    def push_menu(self, canonical_menu: CanonicalMenu) -> SyncResult:
        """Push a canonical menu to the external channel."""
        ...

    @abstractmethod
    def pull_menu(self) -> CanonicalMenu:
        """Pull the current menu from the external channel."""
        ...

    # ── Orders ─────────────────────────────────────────────────

    @abstractmethod
    def normalize_inbound_order(self, raw_payload: dict) -> CanonicalOrder:
        """Convert a channel-specific payload into a CanonicalOrder."""
        ...

    @abstractmethod
    def update_order_status(
        self, external_order_id: str, status: str, reason: str = ""
    ) -> bool:
        """Notify the external channel of an order status change."""
        ...

    # ── Availability ───────────────────────────────────────────

    @abstractmethod
    def update_availability(
        self, items: list[dict], available: bool
    ) -> SyncResult:
        """Toggle availability for a list of items on the channel."""
        ...

    # ── Credentials ────────────────────────────────────────────

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Test that stored credentials are valid."""
        ...

    # ── Webhooks ───────────────────────────────────────────────

    @abstractmethod
    def verify_webhook_signature(
        self, payload: bytes, headers: dict
    ) -> bool:
        """Verify the inbound webhook signature."""
        ...

    @abstractmethod
    def handle_webhook(
        self, event_type: str, payload: dict, headers: dict
    ) -> WebhookResult:
        """Process an inbound webhook event."""
        ...

    # ── Menu change webhooks (optional) ────────────────────────

    def handle_menu_webhook(
        self, event_type: str, payload: dict, headers: dict
    ) -> WebhookResult:
        """
        Handle inbound menu/item change events from external channels.

        Override in adapters that receive product updates via webhook
        (e.g., POS systems pushing menu changes).

        Supported event patterns: menu.updated, item.updated,
        item.created, item.deleted, item.86d (86'd/unavailable).
        """
        return WebhookResult(
            success=True,
            action="not_implemented",
            message=f"Menu webhook '{event_type}' not implemented for this adapter.",
        )

    # ── Lifecycle hooks (optional) ─────────────────────────────

    def on_link_activated(self) -> None:
        """Called when a ChannelLink is activated."""

    def on_link_deactivated(self) -> None:
        """Called when a ChannelLink is deactivated."""
