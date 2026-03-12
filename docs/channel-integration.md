# Channel Integration Architecture

## Overview

The channel integration system connects your POS with external platforms (UberEats, DoorDash, Square, etc.) through a **hub-and-spoke adapter pattern**. Every external system — including your own internal POS — connects through the same standardized interface. No special-casing in core code.

```
External POS (Square, Toast)        Delivery Channels (UberEats, DoorDash)
        |                                       |
   POS Adapters                          Channel Adapters
        |                                       |
        +------------- Adapter Registry --------+
                            |
                   Canonical Data Layer
                   (CanonicalMenu, CanonicalOrder)
                            |
              +-------------+-------------+
              |             |             |
         orders app    integrations    webhooks app
              |             |             |
              +--- products / locations / channels ---+
```

---

## Core Concepts

### 1. Channel (SHARED app)

A **Channel** is a global definition of an external platform. It lives in the `public` schema — shared across all tenants.

```
channels/models.py → Channel
```

| Field | Purpose |
|-------|---------|
| `slug` | Unique identifier (e.g. `internal_pos`, `ubereats`, `doordash`) |
| `display_name` | Human-readable name |
| `channel_type` | `marketplace` / `pos` / `direct` / `custom` |
| `direction` | `inbound` (orders come in), `outbound` (menu goes out), `bidirectional` |
| `adapter_class` | Dotted Python path to the adapter (e.g. `integrations.adapters.internal.InternalPOSAdapter`) |
| `config_schema` | JSON Schema defining what credentials this channel needs |
| `is_active` | Enable/disable globally |

Channels are **read-only** via the API — created by admins or seed scripts.

**API:** `GET /api/v1/channels/` (no tenant header required)

---

### 2. ChannelLink (TENANT app)

A **ChannelLink** binds a Channel to a specific Location within a merchant's tenant. It holds the credentials and tracks sync status.

```
integrations/models.py → ChannelLink
```

| Field | Purpose |
|-------|---------|
| `channel` | FK → Channel (which platform) |
| `location` | FK → Location (which store) |
| `credentials` | JSONField — API keys, tokens, secrets for this connection |
| `external_store_id` | The store/restaurant ID on the external platform |
| `is_active` | Enable/disable this specific link |
| `sync_status` | `pending` / `syncing` / `synced` / `error` |
| `sync_error` | Last error message |
| `last_sync_at` | Timestamp of last successful sync |

**Unique constraint:** One channel per location (can't link UberEats twice to the same store).

**Single POS per location:** `ChannelLink.save()` rejects activating a second POS-type (`channel.channel_type == "pos"`) link at the same location. Different locations under the same merchant can use different POS systems. Marketplace/direct channels are unlimited.

**API:** `GET/POST/PUT/DELETE /api/v1/channel-links/` (requires `X-Tenant-ID`)

---

### 3. ProductChannelConfig (TENANT app)

Per-product, per-channel overrides. Allows different pricing and availability on different channels. **Writes through to `ProductLocation.channels` JSONField on save** to maintain a single source of truth for pricing resolution.

```
integrations/models.py → ProductChannelConfig
```

| Field | Purpose |
|-------|---------|
| `product_location` | FK → ProductLocation |
| `channel` | FK → Channel |
| `price` | Override price in cents (null = use default). Synced to `ProductLocation.channels[slug]["price"]` on save. |
| `is_available` | Override availability for this channel. Synced to `ProductLocation.channels[slug]["is_available"]` on save. |
| `external_product_id` | Product ID on the external platform |
| `extra_data` | Any channel-specific metadata |

**Write-through behavior:** On `save()`, the model calls `_sync_to_product_location()` which updates `ProductLocation.channels` JSONField. On `delete()`, it removes the channel entry from the JSONField.

**Example:** A burger costs 999 cents in-store but 1199 cents on UberEats (to cover commission).

**API:** `GET/POST/PUT/DELETE /api/v1/product-channel-configs/` (requires `X-Tenant-ID`)

---

## Adapter Framework

### AbstractChannelAdapter

Every channel adapter must subclass this and implement all abstract methods:

```
integrations/adapters/base.py → AbstractChannelAdapter
```

```python
class AbstractChannelAdapter(ABC):
    def __init__(self, channel_link: ChannelLink):
        self.channel_link = channel_link
        self.credentials = channel_link.credentials
        self.location = channel_link.location

    # Menu operations
    def push_menu(canonical_menu) → SyncResult       # Send menu to external system
    def pull_menu() → CanonicalMenu                   # Fetch menu from external system

    # Order operations
    def normalize_inbound_order(raw_payload) → CanonicalOrder   # Parse incoming order
    def update_order_status(external_id, status) → bool         # Notify status change

    # Availability
    def update_availability(items, available) → SyncResult      # Toggle item availability

    # Credentials
    def validate_credentials() → bool                           # Test API keys work

    # Webhooks
    def verify_webhook_signature(payload, headers) → bool       # Verify inbound signature
    def handle_webhook(event_type, payload, headers) → WebhookResult

    # Menu change webhooks (optional — default no-op)
    def handle_menu_webhook(event_type, payload, headers) → WebhookResult

    # Lifecycle (optional)
    def on_link_activated()
    def on_link_deactivated()
```

### IntegrationSyncService

Orchestrates sync operations between external channels and the local database.

```
integrations/services.py → IntegrationSyncService
```

| Method | Purpose |
|--------|---------|
| `pull_and_persist(channel_link)` | Calls `adapter.pull_menu()` → converts `CanonicalMenu` → upserts products, categories, modifiers into local DB. Assigns products to the channel link's location with channel-specific pricing. Maps external IDs via `ProductChannelConfig`. Stamps `Product.managed_by` based on channel type: POS channels stamp their slug (e.g. `"clover"`), marketplace channels stamp `"internal_pos"`. Respects ownership precedence (never downgrades). |
| `push_to_active_channels(location)` | Pushes menu to all active non-POS channel links for a location. Skips all `channel_type="pos"` channels (catalog push to POS reverses the intended data flow). Called by product mutation signals. |

### Product Mutation Signals

```
integrations/signals.py
```

Django signals connected via `IntegrationsConfig.ready()`:

| Signal | Sender | Action |
|--------|--------|--------|
| `post_save` | `ProductLocation` | Triggers `push_to_active_channels()` for the location |
| `post_delete` | `ProductLocation` | Triggers `push_to_active_channels()` for the location |

This ensures that when products are added/updated/removed at a location (via POS sync, API, or admin), all connected channels are automatically notified.

### AdapterRegistry

Dynamically imports and caches adapter classes by their dotted path. Used throughout the codebase to get the right adapter for a ChannelLink.

```
integrations/adapters/__init__.py → AdapterRegistry
```

```python
# Get an adapter instance for a channel link
adapter = AdapterRegistry.get_adapter(channel_link)

# The registry:
# 1. Reads channel_link.channel.adapter_class (e.g. "integrations.adapters.internal.InternalPOSAdapter")
# 2. Dynamically imports the class
# 3. Validates it's a subclass of AbstractChannelAdapter
# 4. Caches the class for future lookups
# 5. Returns an instance initialized with the channel_link
```

### InternalPOSAdapter (Reference Implementation)

Your internal POS is just another adapter. Since the database IS the source of truth, most operations are no-ops:

```
integrations/adapters/internal.py → InternalPOSAdapter
```

| Method | Behavior |
|--------|----------|
| `push_menu()` | No-op — menu is the database |
| `pull_menu()` | Builds CanonicalMenu from Product queryset |
| `normalize_inbound_order()` | Delegates to `CanonicalOrder.from_dict()` |
| `update_order_status()` | No-op — returns True |
| `update_availability()` | Updates `ProductLocation.is_available` directly |
| `validate_credentials()` | Always True |

---

## Canonical Data Layer

All data flowing between adapters and core business logic uses **canonical dataclasses** — channel-agnostic representations that normalize the differences between platforms.

### CanonicalMenu

```
integrations/canonical/menu.py
```

```
CanonicalMenu
├── location_id, location_name, channel_slug
├── categories: ["Burgers", "Drinks"]
└── products: [
      CanonicalProduct
      ├── plu, name, description, price (cents)
      ├── image_url, is_available, category_name
      ├── tax_rate_percentage, external_id, sort_order
      └── modifier_groups: [
            CanonicalModifierGroup
            ├── plu, name, min_select, max_select
            └── modifiers: [
                  CanonicalModifier { plu, name, price, is_available }
                ]
          ]
    ]
```

**Key method:** `CanonicalMenu.from_product_queryset(queryset, location, channel_slug)` — builds the full menu from your Product models with location-specific pricing and modifier groups.

### CanonicalOrder

```
integrations/canonical/orders.py
```

```
CanonicalOrder
├── external_order_id, order_type
├── customer: name, phone, email
├── delivery_address
├── financials: subtotal, tax_total, delivery_fee, service_fee, tip, discount_total, total
├── timing: placed_at, estimated_prep_time, estimated_delivery_time
├── notes, raw_payload
└── items: [
      CanonicalOrderItem
      ├── plu, name, quantity, unit_price (cents)
      ├── notes, external_item_id
      ├── total_price (computed: unit_price * quantity + modifier totals)
      └── modifiers: [
            CanonicalOrderModifier { plu, name, quantity, unit_price, group_name }
          ]
    ]
```

**Key methods:**
- `CanonicalOrder.from_dict(data)` — parse from any dict/JSON (used by adapters)
- `canonical_order.to_order_kwargs()` — convert to `Order.objects.create()` kwargs
- `canonical_order.to_dict()` — serialize back to dict

### Result Types

```
integrations/canonical/results.py
```

- **`SyncResult`** — returned by `push_menu()`, `update_availability()`:
  `success`, `message`, `updated_count`, `created_count`, `errors[]`, `external_ids[]`

- **`WebhookResult`** — returned by `handle_webhook()`:
  `success`, `action`, `message`, `order_id`

---

## Data Flow: Menu Sync

When a merchant pushes their menu to an external channel:

```
1. POST /api/v1/channel-links/{id}/sync_menu/
                    │
2. ChannelLinkViewSet.sync_menu()
                    │
3. AdapterRegistry.get_adapter(channel_link)
   → imports "integrations.adapters.ubereats.UberEatsAdapter"
   → returns UberEatsAdapter(channel_link)
                    │
4. Product.objects.filter(locations__location=link.location)
   → CanonicalMenu.from_product_queryset(queryset, location, "ubereats")
   → Builds normalized menu with location-specific prices
                    │
5. adapter.push_menu(canonical_menu)
   → Adapter converts CanonicalMenu → UberEats API format
   → Calls UberEats Menu API
   → Returns SyncResult(success=True, updated_count=42)
                    │
6. Update channel_link.sync_status = "synced"
   Update channel_link.last_sync_at = now
                    │
7. Return SyncResult to client
```

---

## Data Flow: Pull Menu from External POS

When a merchant imports/syncs products from an external POS (e.g. Clover, Square):

```
1. POST /api/v1/channel-links/{id}/pull_menu/
                    │
2. IntegrationSyncService.pull_and_persist(channel_link)
                    │
3. adapter.pull_menu()
   → Calls external POS API (e.g. Clover Menu API)
   → Returns CanonicalMenu (normalized products, categories, modifiers)
                    │
4. For each category in CanonicalMenu:
   → Category.objects.update_or_create()
                    │
5. For each product in CanonicalMenu:
   → Product.objects.update_or_create(plu=...) — upsert by PLU
   → ProductLocation.get_or_create(product, location)
   → ProductLocation.set_channel_data(channel_slug, price, is_available)
   → ProductChannelConfig.update_or_create() — map external_product_id
                    │
6. For each modifier group + modifier:
   → Create/update Product (type=MODIFIER_GROUP / MODIFIER_ITEM)
   → Create ProductRelation (parent→child links)
   → Create ProductLocation for modifiers at same location
                    │
7. Update channel_link.sync_status = "synced"
   Update channel_link.last_sync_at = now
                    │
8. Return SyncResult { created: N, updated: M }
```

---

## Data Flow: Auto-Push on Product Change

When products change locally, all connected channels are automatically notified:

```
1. Product updated via API / bulk_sync / admin
   → ProductLocation saved or deleted
                    │
2. Django signal fires (post_save / post_delete on ProductLocation)
   → integrations.signals.on_product_location_saved()
                    │
3. IntegrationSyncService.push_to_active_channels(location)
   → Finds all active ChannelLinks for this location
   → Skips all POS-type channels (catalog push to POS reverses intended data flow)
                    │
4. For each active channel link:
   → Build CanonicalMenu from local products
   → adapter.push_menu(canonical_menu)
   → Update sync_status / sync_error / last_sync_at
```

---

## Data Flow: Inbound Menu Webhook

When an external POS/channel pushes menu changes via webhook:

```
1. POST /api/v1/webhooks/inbound/{channel_link_id}/
   X-Event-Type: menu.updated  (or item.86d, item.created, etc.)
                    │
2. InboundWebhookView.post()
   → Resolves tenant from ChannelLink
   → Verifies webhook signature
                    │
3. adapter.handle_webhook(event_type, payload, headers)
   → Routes menu.* / item.* events to handle_menu_webhook()
                    │
4. adapter.handle_menu_webhook()
   → For "item.86d": directly marks products unavailable at location
   → For "menu.updated": calls IntegrationSyncService.pull_and_persist()
     to re-sync the full menu from the external system
                    │
5. WebhookLog recorded with result
```

---

## Data Flow: Inbound Order (Webhook)

When an order arrives from an external channel:

```
1. POST /api/v1/webhooks/inbound/{channel_link_id}/
   (No JWT auth — signature-verified)
                    │
2. InboundWebhookView.post()
   → Iterate tenant schemas to find the ChannelLink
   → Switch to correct tenant schema
                    │
3. adapter.verify_webhook_signature(body, headers)
   → Validates HMAC / API signature
                    │
4. adapter.handle_webhook(event_type, payload, headers)
   → Adapter parses the channel-specific payload
   → For "new_order" events:
                    │
5. adapter.normalize_inbound_order(payload)
   → Converts UberEats order JSON → CanonicalOrder
                    │
6. OrderService.create_order_from_canonical(
       canonical_order, location, channel, channel_link
   )
   → Creates Order + OrderItems + OrderModifiers
   → Creates initial OrderStatusLog (RECEIVED)
                    │
7. WebhookLog.objects.create(direction="inbound", ...)
   → Log stored for debugging/auditing
                    │
8. Return WebhookResult → 200 OK
```

---

## Data Flow: Order Status Update

When a merchant updates an order status (e.g. accepts an UberEats order):

```
1. PATCH /api/v1/orders/{id}/status/
   { "status": "accepted" }
                    │
2. OrderService.transition_status(order, "accepted")
   → Validates against VALID_TRANSITIONS state machine
   → Sets order.accepted_at = now
   → Creates OrderStatusLog
                    │
3. If order has a channel_link:
   adapter = AdapterRegistry.get_adapter(order.channel_link)
   adapter.update_order_status(order.external_order_id, "accepted")
   → Notifies UberEats that merchant accepted the order
```

### Order State Machine

```
RECEIVED → ACCEPTED → PREPARING → READY → PICKED_UP → DELIVERED → COMPLETED
    │          │           │         │          │
    ├→ REJECTED  ├→ CANCELLED  ├→ CANCELLED ├→ CANCELLED  ├→ FAILED
    ├→ CANCELLED ├→ FAILED    ├→ FAILED   ├→ FAILED    ├→ COMPLETED
    └→ FAILED                             └→ COMPLETED
```

Terminal states (no further transitions): `COMPLETED`, `REJECTED`, `CANCELLED`, `FAILED`

---

## Adding a New Channel Adapter

### Step 1: Create the adapter

```python
# integrations/adapters/ubereats.py

from integrations.adapters.base import AbstractChannelAdapter
from integrations.canonical.menu import CanonicalMenu
from integrations.canonical.orders import CanonicalOrder
from integrations.canonical.results import SyncResult, WebhookResult


class UberEatsAdapter(AbstractChannelAdapter):

    def push_menu(self, canonical_menu):
        # Convert canonical_menu.to_dict() → UberEats Menu API format
        # Call UberEats API: PUT /v2/eater/store/{store_id}/menus
        api_key = self.credentials.get("api_key")
        store_id = self.channel_link.external_store_id
        # ... make API call ...
        return SyncResult(success=True, message="Menu pushed")

    def pull_menu(self):
        # Call UberEats API: GET /v2/eater/store/{store_id}/menus
        # Convert response → CanonicalMenu
        ...

    def normalize_inbound_order(self, raw_payload):
        # Convert UberEats order webhook payload → CanonicalOrder
        return CanonicalOrder(
            external_order_id=raw_payload["id"],
            order_type="delivery",
            items=[...],
            customer_name=raw_payload["eater"]["first_name"],
            total=raw_payload["total"],
            raw_payload=raw_payload,
        )

    def update_order_status(self, external_order_id, status, reason=""):
        # Call UberEats API: POST /v1/eater/orders/{id}/status
        ...
        return True

    def update_availability(self, items, available):
        # Call UberEats API: POST /v2/eater/store/{id}/items/availability
        ...
        return SyncResult(success=True, updated_count=len(items))

    def validate_credentials(self):
        # Call UberEats API with stored credentials to verify they work
        ...
        return True

    def verify_webhook_signature(self, payload, headers):
        # Verify UberEats HMAC signature from X-Uber-Signature header
        import hmac, hashlib
        secret = self.credentials.get("webhook_secret", "")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, headers.get("X-Uber-Signature", ""))

    def handle_webhook(self, event_type, payload, headers):
        if event_type == "orders.notification":
            canonical = self.normalize_inbound_order(payload)
            from orders.services import OrderService
            order = OrderService.create_order_from_canonical(
                canonical, self.location,
                channel=self.channel_link.channel,
                channel_link=self.channel_link,
            )
            return WebhookResult(success=True, action="order_created", order_id=str(order.id))
        elif event_type.startswith("menu.") or event_type.startswith("item."):
            return self.handle_menu_webhook(event_type, payload, headers)
        return WebhookResult(success=True, action="ignored")

    def handle_menu_webhook(self, event_type, payload, headers):
        # Handle menu/item change events from the external platform
        if event_type == "item.86d":
            # Directly mark items unavailable
            from products.models import ProductLocation
            for item in payload.get("items", []):
                ProductLocation.objects.filter(
                    product__plu=item["plu"], location=self.location
                ).update(is_available=False)
            return WebhookResult(success=True, action="items_86d")

        # For menu.updated, re-sync the full menu
        from integrations.services import IntegrationSyncService
        result = IntegrationSyncService.pull_and_persist(self.channel_link)
        return WebhookResult(success=result.success, action="menu_synced", message=result.message)
```

### Step 2: Register the channel

```python
from channels.models import Channel

Channel.objects.create(
    slug="ubereats",
    display_name="Uber Eats",
    channel_type="marketplace",
    direction="bidirectional",
    adapter_class="integrations.adapters.ubereats.UberEatsAdapter",
    config_schema={
        "type": "object",
        "required": ["api_key", "client_secret", "webhook_secret"],
        "properties": {
            "api_key": {"type": "string"},
            "client_secret": {"type": "string"},
            "webhook_secret": {"type": "string"}
        }
    },
    is_active=True,
)
```

### Step 3: Link it to a location (per-tenant)

```
POST /api/v1/channel-links/
X-Tenant-ID: <merchant-uuid>

{
    "channel": "<ubereats-channel-uuid>",
    "location": "<location-uuid>",
    "external_store_id": "uber-store-12345",
    "credentials": {
        "api_key": "...",
        "client_secret": "...",
        "webhook_secret": "..."
    }
}
```

### Step 4: Configure webhook URL on the external platform

Give the external platform your inbound webhook URL:
```
https://your-domain.com/api/v1/webhooks/inbound/<channel-link-uuid>/
```

This URL requires no JWT — authentication is handled by `verify_webhook_signature()`.

---

## Multi-Tenancy

| App | Schema Type | Why |
|-----|-------------|-----|
| `channels` | SHARED (public) | Channel definitions are global — all tenants see the same list of available platforms |
| `integrations` | TENANT | Each merchant has their own ChannelLinks, credentials, and ProductChannelConfigs |
| `orders` | TENANT | Orders are fully isolated per merchant |
| `webhooks` | TENANT | Webhook endpoints and logs are per-merchant |

The inbound webhook endpoint (`/api/v1/webhooks/inbound/<link_id>/`) is **tenant-exempt** — it resolves the tenant automatically by looking up which schema the ChannelLink exists in.

---

## Catalog Ownership (POS-as-Master)

The system enforces a **single active POS per location** with **per-product write protection**. This follows the industry standard pattern used by Deliverect, Square, Toast, and Lightspeed, but extends it to support mixed POS setups across locations.

### How It Works

```
                        ┌─────────────────────────────────────────────────┐
                        │              Product Data Layers                │
                        ├─────────────────────────────────────────────────┤
                        │                                                 │
                        │  POS-OWNED (read-only per product.managed_by)   │
                        │  ┌─────────────────────────────────────┐       │
                        │  │ name, price, description, sku,      │       │
                        │  │ plu, product_type, category,         │       │
                        │  │ tax_rate, image, modifiers           │       │
                        │  └─────────────────────────────────────┘       │
                        │                                                 │
                        │  PLATFORM-OWNED (always writable)               │
                        │  ┌─────────────────────────────────────┐       │
                        │  │ ProductLocation.price_override       │       │
                        │  │ ProductLocation.channels[ch].price   │       │
                        │  │ ProductLocation.channels[ch].avail   │       │
                        │  │ ProductLocation.is_available          │       │
                        │  │ Product.visible                      │       │
                        │  │ MenuItem.price_override              │       │
                        │  │ Menu curation (items, categories)    │       │
                        │  └─────────────────────────────────────┘       │
                        │                                                 │
                        └─────────────────────────────────────────────────┘
```

### Per-Location POS Enforcement

Each location can have **at most one active POS-type ChannelLink**. Different locations under the same merchant can use different POS systems.

```
Merchant: "Pizza Chain"
├── Location A (Downtown)  → Clover POS (ChannelLink, channel_type="pos")
├── Location B (Mall)      → Square POS (ChannelLink, channel_type="pos")
├── Location C (Airport)   → Internal POS (no POS ChannelLink, or internal_pos link)
```

Enforced by `ChannelLink.save()`. Marketplace/direct channels are unlimited per location.

There is **no merchant-level `catalog_source` field**. POS ownership is derived from ChannelLinks per location and tracked per product via `managed_by`.

### Product.managed_by

Tracks catalog ownership of each product. The `INTERNAL_POS_SLUG` constant (`"internal_pos"`) lives in `common/constants.py`.

| Value | Meaning | Core Fields | How It Gets Set |
|-------|---------|-------------|-----------------|
| `"internal_pos"` | Platform-owned (locally created OR seeded from marketplace) | Fully writable | API product creation, marketplace pulls (UberEats, DoorDash) |
| Any external POS slug (e.g. `"clover"`, `"square"`) | Imported from that POS via `pull_menu` | Read-only | POS pulls (Clover, Square, Toast) |
| `""` (empty) | Legacy/transitional | Fully writable (treated same as `"internal_pos"`) | Pre-existing data only |

**Ownership precedence:** external POS > `"internal_pos"` > `""` (never downgrade). If a product is already owned by an external POS (e.g. `"clover"`), a marketplace pull will not overwrite it to `"internal_pos"`.

**Marketplace seed behavior:** Pulling from a marketplace channel (UberEats, DoorDash) stamps `managed_by="internal_pos"` — the platform becomes the source of truth for those products, and they remain fully editable via the API.

**POS pull behavior:** Pulling from a POS channel (Clover, Square) stamps the POS slug (e.g. `managed_by="clover"`) — the external POS owns the catalog, and core fields become read-only.

Stamped by `IntegrationSyncService.pull_and_persist()`. Read-only via API.

### Write Protection (CatalogWriteProtectionMixin)

Applied to `ProductViewSet`. Protection is **per-product** based on `Product.managed_by`:

| Action | Platform-owned (`managed_by="internal_pos"` or `""`) | External POS-managed (`managed_by="clover"`) |
|--------|------------------------------------------------------|----------------------------------------------|
| `GET /products/` | Yes | Yes |
| `POST /products/` | Yes (always allowed, stamped `"internal_pos"`) | N/A (create is always platform-owned) |
| `DELETE /products/{plu}/` | Yes | **No** — remove from POS, re-sync |
| `PATCH` core fields (name, price, etc.) | Yes | **No** — update in POS, re-sync |
| `PATCH` platform fields (visible, etc.) | Yes | Yes |
| `POST /products/bulk_delete/` | Yes | **No** (per-product check) |
| `POST /products/bulk_sync/` | Yes | Yes (used by pull_and_persist internally) |
| `update_location_pricing` | Yes | Yes |
| `mark_unavailable` | Yes | Yes |
| Menu curation (all `/menus/`) | Yes | Yes |

### Data Flow: Mixed POS Example

```
1. Merchant has 3 locations, all start with internal POS
   → Full product CRUD for all locations

2. Location A activates Clover ChannelLink (channel_type="pos")
   → ChannelLink.save() validates: no other active POS at Location A
   → Location B and C unaffected

3. POST /channel-links/{clover-link-id}/pull_menu/
   → Products imported with managed_by = "clover"
   → Those specific products become read-only for core fields
   → Platform-owned products (managed_by="internal_pos") remain fully writable

4. Location B activates Square ChannelLink (channel_type="pos")
   → OK — different location, no conflict with Clover at Location A

5. Merchant creates new product via POST /products/
   → Always allowed (managed_by="internal_pos" = platform-owned)
   → Can be assigned to any location including Clover/Square ones

6. Merchant pulls menu from UberEats (marketplace channel)
   → Products seeded with managed_by = "internal_pos"
   → Platform becomes source of truth — products remain fully editable
   → Existing Clover-managed products are NOT downgraded (ownership precedence)

7. Merchant tries PATCH /products/{clover-plu}/ {name: "New"}
   → 403: "This product is managed by clover."

8. Merchant does PATCH /products/{local-plu}/ {name: "New"}
   → 200: OK — platform-owned (managed_by="internal_pos"), fully writable
```

---

## API Reference

| Endpoint | Method | Auth | Tenant | Description |
|----------|--------|------|--------|-------------|
| `/api/v1/channels/` | GET | JWT | No | List available channels |
| `/api/v1/channels/{id}/` | GET | JWT | No | Channel detail |
| `/api/v1/channel-links/` | GET/POST | JWT | Yes | List/create channel links |
| `/api/v1/channel-links/{id}/` | GET/PUT/PATCH/DELETE | JWT | Yes | Manage a link |
| `/api/v1/channel-links/{id}/validate/` | POST | JWT | Yes | Test credentials |
| `/api/v1/channel-links/{id}/sync_menu/` | POST | JWT | Yes | Push menu to channel (outbound) |
| `/api/v1/channel-links/{id}/pull_menu/` | POST | JWT | Yes | Pull menu from channel and persist locally (inbound) |
| `/api/v1/product-channel-configs/` | GET/POST | JWT | Yes | List/create price overrides (writes through to ProductLocation.channels) |
| `/api/v1/product-channel-configs/{id}/` | GET/PUT/PATCH/DELETE | JWT | Yes | Manage overrides (writes through to ProductLocation.channels) |
| `/api/v1/orders/` | GET/POST | JWT | Yes | List/create orders |
| `/api/v1/orders/{id}/` | GET | JWT | Yes | Order detail |
| `/api/v1/orders/{id}/status/` | PATCH | JWT | Yes | Update order status |
| `/api/v1/webhooks/inbound/{link_id}/` | POST | Signature | Auto | Receive external webhooks (orders + menu events) |
| `/api/v1/webhooks/endpoints/` | GET/POST | JWT | Yes | Manage outbound webhooks |
| `/api/v1/webhooks/logs/` | GET | JWT | Yes | View webhook logs |
