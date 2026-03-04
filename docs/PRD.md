# Integration Framework — Product Requirements Document

## Context

The current Django codebase has a strong product catalog and menu management foundation but lacks the plugin architecture needed to connect with external POS systems and delivery channels. Channel data is stored as free-form JSON strings (`ProductLocation.channels`, `Product.channel_overrides`) with no adapter abstraction, no order management, and no webhook infrastructure. This plan introduces a hub-and-spoke integration framework where every external system (own POS, Square, UberEats, etc.) connects through a standardized adapter interface.

---

## Architecture

```
External POS (Square, Toast)        Delivery Channels (UberEats, DoorDash)
        |                                       |
   POS Adapters                          Channel Adapters
        |                                       |
        +------------- Adapter Registry --------+
                            |
                   Canonical Data Layer
                   (dataclasses: CanonicalMenu, CanonicalOrder)
                            |
              +-------------+-------------+
              |             |             |
         orders app    integrations    webhooks app
         (TENANT)      (TENANT)       (TENANT)
              |             |             |
              +--- existing products/locations/channels apps ---+
```

**Key principle:** Your internal POS is just another adapter (`InternalPOSAdapter`) implementing the same interface as `UberEatsAdapter` or `SquareAdapter`. No special-casing in core code.

---

## New Apps

| App | Type | Purpose |
|---|---|---|
| `channels` | SHARED | `Channel` model — global registry of available integrations |
| `integrations` | TENANT | `ChannelLink`, `ProductChannelConfig`, adapter code, canonical dataclasses |
| `orders` | TENANT | `Order`, `OrderItem`, `OrderModifier`, `OrderStatusLog`, `OrderService` |
| `webhooks` | TENANT | `WebhookEndpoint`, `WebhookLog`, inbound receivers, outbound dispatch |

Split `channels`/`integrations` because django-tenants requires all models in one app to be either SHARED or TENANT.

---

## Implementation Plan

### Phase 1: Foundation — channels + integrations apps

#### 1a. Create `channels` app (SHARED)

**New file: `channels/models.py`**
- `Channel` model: `slug` (unique), `display_name`, `channel_type` (MARKETPLACE/POS/DIRECT/CUSTOM), `direction` (INBOUND/OUTBOUND/BIDIRECTIONAL), `adapter_class` (dotted path), `config_schema` (JSONField), `is_active`, `icon_url`
- Seed data: `internal_pos`, `ubereats`, `doordash`, `square`, `toast` (stubs)

**New files:** `channels/serializers.py`, `channels/views.py` (read-only ChannelViewSet), `channels/urls.py`, `channels/admin.py`

#### 1b. Create `integrations` app (TENANT)

**New file: `integrations/models.py`**
- `ChannelLink`: FK→Channel, FK→Location, `credentials` (JSONField), `external_store_id`, `is_active`, `sync_status`, `sync_error`, `last_sync_at`. Unique constraint on (channel, location).
- `ProductChannelConfig`: FK→ProductLocation, FK→Channel, `price` (cents, nullable), `is_available`, `external_product_id`, `extra_data` (JSONField). Unique constraint on (product_location, channel).

**New file: `integrations/adapters/base.py`** — `AbstractChannelAdapter` ABC:
- `__init__(self, channel_link)` — stores link, credentials, location
- `push_menu(canonical_menu) → SyncResult`
- `pull_menu() → CanonicalMenu`
- `normalize_inbound_order(raw_payload) → CanonicalOrder`
- `update_order_status(external_order_id, status, reason) → bool`
- `update_availability(items, available) → SyncResult`
- `validate_credentials() → bool`
- `verify_webhook_signature(payload, headers) → bool`
- `handle_webhook(event_type, payload, headers) → WebhookResult`
- Optional hooks: `on_link_activated()`, `on_link_deactivated()`

**New file: `integrations/adapters/__init__.py`** — `AdapterRegistry`:
- `get_adapter_class(dotted_path)` — import + cache + validate subclass
- `get_adapter(channel_link)` — instantiate adapter for a link
- `clear_cache()`

**New file: `integrations/adapters/internal.py`** — `InternalPOSAdapter`:
- `push_menu()` → no-op (menu IS the database)
- `pull_menu()` → builds CanonicalMenu from Product queryset
- `normalize_inbound_order()` → `CanonicalOrder.from_dict(payload)`
- `update_order_status()` → True (no external system)
- `update_availability()` → directly updates ProductLocation.is_available
- `validate_credentials()` → True
- `verify_webhook_signature()` → True
- `handle_webhook()` → no-op

**New file: `integrations/canonical/menu.py`** — dataclasses:
- `CanonicalModifier(plu, name, price, is_available, external_id, sort_order)`
- `CanonicalModifierGroup(plu, name, min_select, max_select, modifiers, sort_order)`
- `CanonicalProduct(plu, name, description, price, image_url, is_available, category_name, modifier_groups, tax_rate_percentage, external_id, sort_order)` + `to_dict()`
- `CanonicalMenu(location_id, location_name, channel_slug, products, categories)` + `from_product_queryset(queryset, location)` + `to_dict()`

**New file: `integrations/canonical/orders.py`** — dataclasses:
- `CanonicalOrderModifier(plu, name, quantity, unit_price, group_name, group_plu)`
- `CanonicalOrderItem(plu, name, quantity, unit_price, notes, modifiers, external_item_id)` + `total_price` property
- `CanonicalOrder(external_order_id, order_type, items, customer_*, delivery_address, subtotal, tax_total, delivery_fee, service_fee, tip, discount_total, total, placed_at, estimated_*, notes, raw_payload)` + `from_dict()` + `to_order_kwargs()`

**New file: `integrations/canonical/results.py`**:
- `SyncResult(success, message, updated_count, created_count, errors, external_ids)`
- `WebhookResult(success, action, message, order_id)`

**New files:** `integrations/serializers.py`, `integrations/views.py` (ChannelLinkViewSet with `validate` and `sync_menu` actions), `integrations/urls.py`, `integrations/admin.py`

#### 1c. Modify existing files

- **`backend/settings.py`**: Add `channels` to `SHARED_APPS`, `integrations` to `TENANT_APPS`
- **`backend/api_v1_urls.py`**: Add `include("channels.urls")`, `include("integrations.urls")`
- **`accounts/middleware.py`**: Add `/api/v1/channel-links/` to `TENANT_ONLY_PREFIXES`

---

### Phase 2: Orders app

**New file: `orders/models.py`**:
- `OrderStatus` TextChoices: RECEIVED, ACCEPTED, PREPARING, READY, PICKED_UP, DELIVERED, COMPLETED, REJECTED, CANCELLED, FAILED
- `OrderType` TextChoices: DELIVERY, TAKEAWAY, EAT_IN, PICKUP
- `VALID_TRANSITIONS` dict — enforces state machine
- `Order`: order_number (unique, auto-gen), external_order_id, FK→Channel (nullable), FK→ChannelLink (nullable), FK→Location, status, order_type, customer_* fields, financial fields (subtotal/tax/fees/tip/discount/total in cents), timing fields (placed_at, accepted_at, ready_at, picked_up_at, delivered_at, estimated_*), notes, raw_payload. Indexes on (status, location), (channel, external_order_id), (-placed_at).
- `OrderItem`: FK→Order, FK→Product (SET_NULL), plu (snapshot), name (snapshot), quantity, unit_price, total_price, tax_amount, notes, sort_order, external_item_id
- `OrderModifier`: FK→OrderItem, FK→Product (SET_NULL), plu, name, quantity, unit_price, total_price, group_name, group_plu
- `OrderStatusLog`: FK→Order, from_status, to_status, changed_by, reason, timestamp

**New file: `orders/services.py`** — `OrderService`:
- `create_order_from_canonical(canonical_order, location, channel, channel_link)` — atomic, creates Order + items + modifiers + initial status log
- `transition_status(order, new_status, changed_by, reason)` — validates against VALID_TRANSITIONS, sets timestamp fields, creates log entry
- `_generate_order_number()` — `ORD-{8-char-hex}`

**New files:** `orders/serializers.py`, `orders/views.py` (OrderViewSet with `status` action), `orders/urls.py`, `orders/admin.py`

#### Modify existing files
- **`backend/settings.py`**: Add `orders` to `TENANT_APPS`
- **`backend/api_v1_urls.py`**: Add `include("orders.urls")`
- **`accounts/middleware.py`**: Add `/api/v1/orders/` to `TENANT_ONLY_PREFIXES`

---

### Phase 3: Channel Data Migration (NOT YET IMPLEMENTED)

Migrate `ProductLocation.channels` JSONField → `ProductChannelConfig` FK model.

**Step 1 — Dual Write:** Modify `ProductLocation.set_channel_data()` to write both JSONField AND create/update `ProductChannelConfig`. Add `_channels_migrated` BooleanField.

**Step 2 — Data Migration:** Management command `migrate_channel_data` iterates all tenants, parses JSON, creates `ProductChannelConfig` rows, sets `_channels_migrated=True`.

**Step 3 — Read from FK:** Update `get_price_for_channel()`, `is_available_on_channel()` to read from `ProductChannelConfig` when migrated.

**Step 4 — Remove JSONField** (later release).

#### Files to modify
- `products/models.py` — ProductLocation: add _channels_migrated, modify channel methods
- `products/serializers.py` — LocationAssignmentSerializer: add channel_configs output
- `products/views.py` — export_menu, mark_unavailable: support both read paths

---

### Phase 4: Webhooks app

**New file: `webhooks/models.py`**:
- `WebhookEndpoint`: url, secret (HMAC), events (JSONField list), is_active
- `WebhookLog`: direction (inbound/outbound), channel_slug, event_type, url, request_headers, request_body, response_status, response_body, success, attempts, next_retry_at, error_message

**New files:** `webhooks/views.py` (inbound receiver resolves tenant from ChannelLink UUID in URL path), `webhooks/dispatcher.py` (outbound with retry), `webhooks/verification.py`

**Inbound webhook URL:** `/api/v1/webhooks/inbound/<channel_link_id>/` — no JWT auth, uses signature verification. Middleware must exempt this path from X-Tenant-ID requirement (tenant resolved from ChannelLink).

#### Files modified
- **`accounts/middleware.py`**: Add TENANT_EXEMPT_PREFIXES for `/api/v1/webhooks/inbound/`
- **`backend/settings.py`**: Add `webhooks` to `TENANT_APPS`
- **`backend/api_v1_urls.py`**: Add `include("webhooks.urls")`

---

### Phase 5: Async Infrastructure

- Add `celery`, `redis`, `django-celery-beat` to `requirements.txt`
- Add Redis to `docker-compose.yml`
- Create `backend/celery.py` app config
- Move webhook dispatch to Celery tasks with exponential backoff retry
- Add periodic task for sync status health checks

---

### Phase 6: Tests

#### Test structure
```
tests/
    channels/test_channel_crud.py
    integrations/
        test_channel_link_crud.py
        test_adapter_registry.py
        test_internal_adapter.py
        test_canonical_models.py
        test_product_channel_config.py
    orders/
        test_order_crud.py
        test_order_service.py
        test_order_state_machine.py
    webhooks/
        test_inbound_webhook.py
        test_outbound_dispatch.py
```

#### Key test scenarios
1. Tenant isolation: orders in tenant A invisible to tenant B
2. State machine: invalid transitions return 400
3. Adapter registry: invalid path raises TypeError
4. Canonical round-trip: from_dict → to_order_kwargs preserves all fields
5. Backward compat: existing product/location tests pass unchanged
6. Webhook tenant resolution: inbound webhook to /webhooks/inbound/<link_id>/ resolves tenant

---

## Data Models

### channels.Channel (SHARED)

Global registry of available channel types.

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `slug` | SlugField (unique) | Machine identifier, e.g. `internal_pos`, `ubereats` |
| `display_name` | CharField | Human-readable name |
| `channel_type` | TextChoices | MARKETPLACE / POS / DIRECT / CUSTOM |
| `direction` | TextChoices | INBOUND / OUTBOUND / BIDIRECTIONAL |
| `adapter_class` | CharField | Dotted Python path to adapter class |
| `config_schema` | JSONField | JSON Schema for required credential fields |
| `is_active` | BooleanField | Whether channel is available for linking |
| `icon_url` | URLField | Optional icon |

### integrations.ChannelLink (TENANT)

Links a Channel to a specific Location within a tenant.

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `channel` | FK → Channel | Which channel type |
| `location` | FK → Location | Which physical location |
| `credentials` | JSONField | Channel-specific auth credentials |
| `external_store_id` | CharField | Store ID on the external platform |
| `is_active` | BooleanField | Whether this link is active |
| `sync_status` | TextChoices | PENDING / SYNCING / SYNCED / ERROR |
| `sync_error` | TextField | Last sync error message |
| `last_sync_at` | DateTimeField | When last sync completed |

**Unique constraint:** `(channel, location)` — one link per channel per location.

### integrations.ProductChannelConfig (TENANT)

Per-product, per-channel pricing and availability overrides.

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `product_location` | FK → ProductLocation | Which product-location combo |
| `channel` | FK → Channel | Which channel |
| `price` | IntegerField (nullable) | Channel-specific price in cents |
| `is_available` | BooleanField | Available on this channel? |
| `external_product_id` | CharField | Product ID on external platform |
| `extra_data` | JSONField | Any other channel-specific metadata |

**Unique constraint:** `(product_location, channel)`

### orders.Order (TENANT)

| Field | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `order_number` | CharField (unique) | Auto-generated `ORD-{8-hex}` |
| `external_order_id` | CharField | ID from external channel |
| `channel` | FK → Channel (nullable) | Source channel |
| `channel_link` | FK → ChannelLink (nullable) | Source link |
| `location` | FK → Location | Which store location |
| `status` | TextChoices | RECEIVED → ACCEPTED → PREPARING → READY → PICKED_UP → DELIVERED → COMPLETED |
| `order_type` | TextChoices | DELIVERY / TAKEAWAY / EAT_IN / PICKUP |
| `customer_*` | Various | Name, phone, email, delivery address |
| `subtotal`, `tax_total`, `delivery_fee`, `service_fee`, `tip`, `discount_total`, `total` | IntegerField | All in cents |
| `placed_at`, `accepted_at`, `ready_at`, `picked_up_at`, `delivered_at` | DateTimeField | Status timestamps |
| `estimated_prep_time` | IntegerField | Minutes |
| `notes` | TextField | Order notes |
| `raw_payload` | JSONField | Original payload from channel |

### orders.OrderItem (TENANT)

| Field | Type | Description |
|---|---|---|
| `order` | FK → Order | Parent order |
| `product` | FK → Product (SET_NULL) | Link to product catalog |
| `plu` | CharField | Snapshot of product PLU at time of order |
| `name` | CharField | Snapshot of product name |
| `quantity` | PositiveIntegerField | How many |
| `unit_price` | IntegerField | Price per unit in cents |
| `total_price` | IntegerField | quantity × unit_price |
| `modifiers` | Reverse FK → OrderModifier | Line item modifiers |

### orders.OrderModifier (TENANT)

| Field | Type | Description |
|---|---|---|
| `order_item` | FK → OrderItem | Parent line item |
| `product` | FK → Product (SET_NULL) | Link to modifier product |
| `plu`, `name` | CharField | Snapshot fields |
| `quantity`, `unit_price`, `total_price` | IntegerField | Pricing |
| `group_name`, `group_plu` | CharField | Which modifier group |

### orders.OrderStatusLog (TENANT)

| Field | Type | Description |
|---|---|---|
| `order` | FK → Order | Parent order |
| `from_status` | CharField | Previous status |
| `to_status` | CharField | New status |
| `changed_by` | CharField | User email or "system" |
| `reason` | TextField | Why the transition happened |
| `timestamp` | DateTimeField | When |

### webhooks.WebhookEndpoint (TENANT)

| Field | Type | Description |
|---|---|---|
| `url` | URLField | Where to send webhooks |
| `secret` | CharField | HMAC signing secret |
| `events` | JSONField | List of subscribed event types |
| `is_active` | BooleanField | Active flag |

### webhooks.WebhookLog (TENANT)

| Field | Type | Description |
|---|---|---|
| `direction` | TextChoices | INBOUND / OUTBOUND |
| `channel_slug` | CharField | Which channel |
| `event_type` | CharField | Event identifier |
| `url` | URLField | Target/source URL |
| `request_headers`, `request_body` | JSONField | Request data |
| `response_status` | IntegerField | HTTP status code |
| `response_body` | TextField | Response text |
| `success` | BooleanField | Whether it succeeded |
| `attempts` | IntegerField | Retry count |
| `error_message` | TextField | Error details |

---

## Order State Machine

```
RECEIVED → ACCEPTED → PREPARING → READY → PICKED_UP → DELIVERED → COMPLETED
    ↓          ↓           ↓         ↓         ↓
 REJECTED   CANCELLED   CANCELLED  CANCELLED  FAILED
 CANCELLED  FAILED      FAILED     FAILED
 FAILED
```

Terminal states: `COMPLETED`, `REJECTED`, `CANCELLED`, `FAILED` — no transitions out.

---

## Adapter Interface

Every channel adapter must extend `AbstractChannelAdapter` and implement:

| Method | Purpose |
|---|---|
| `push_menu(canonical_menu) → SyncResult` | Push menu to channel |
| `pull_menu() → CanonicalMenu` | Pull menu from channel |
| `normalize_inbound_order(raw_payload) → CanonicalOrder` | Convert channel payload to canonical |
| `update_order_status(external_id, status, reason) → bool` | Notify channel of status change |
| `update_availability(items, available) → SyncResult` | Toggle item availability |
| `validate_credentials() → bool` | Test credentials |
| `verify_webhook_signature(payload, headers) → bool` | Verify inbound webhook |
| `handle_webhook(event_type, payload, headers) → WebhookResult` | Process webhook event |

Optional lifecycle hooks: `on_link_activated()`, `on_link_deactivated()`

---

## Canonical Data Layer

Dataclasses that serve as the universal interchange format:

- **CanonicalMenu** — location + products + categories (built from Product queryset)
- **CanonicalProduct** — plu, name, price, modifiers, tax rate
- **CanonicalOrder** — external_id, items, customer info, financials, timing
- **CanonicalOrderItem** — plu, name, quantity, price, modifiers
- **SyncResult** — success, counts, errors
- **WebhookResult** — success, action, order_id

---

## API Endpoints

All under `/api/v1/`:

| Endpoint | Method | Auth | Tenant | Description |
|---|---|---|---|---|
| `channels/` | GET | JWT | No | List available channels |
| `channels/{id}/` | GET | JWT | No | Channel detail |
| `channel-links/` | GET/POST | JWT | Yes | List/create channel links |
| `channel-links/{id}/` | GET/PUT/PATCH/DELETE | JWT | Yes | Manage link |
| `channel-links/{id}/validate/` | POST | JWT | Yes | Validate credentials |
| `channel-links/{id}/sync_menu/` | POST | JWT | Yes | Push menu to channel |
| `product-channel-configs/` | GET/POST | JWT | Yes | Channel-specific product config |
| `product-channel-configs/{id}/` | GET/PUT/PATCH/DELETE | JWT | Yes | Manage config |
| `orders/` | GET/POST | JWT | Yes | List/create orders |
| `orders/{id}/` | GET | JWT | Yes | Order detail (includes items + status logs) |
| `orders/{id}/status/` | PATCH | JWT | Yes | Update order status |
| `webhooks/endpoints/` | GET/POST | JWT | Yes | Manage outbound webhooks |
| `webhooks/endpoints/{id}/` | GET/PUT/DELETE | JWT | Yes | Webhook endpoint detail |
| `webhooks/inbound/{link_id}/` | POST | Signature | Auto | Inbound webhook receiver |
| `webhooks/logs/` | GET | JWT | Yes | View webhook logs |

---

## Critical Files to Modify

| File | Changes |
|---|---|
| `backend/settings.py` | Register 4 new apps, add Celery/Redis config |
| `backend/api_v1_urls.py` | Wire 4 new URL includes |
| `accounts/middleware.py` | Add new TENANT_ONLY_PREFIXES, add TENANT_EXEMPT_PREFIXES for webhooks |
| `products/models.py` | Add _channels_migrated to ProductLocation, modify channel methods for dual-read |
| `products/serializers.py` | Add channel_configs output alongside channels JSONField |
| `products/views.py` | Extend export_menu and mark_unavailable to optionally use adapters |
| `helpers/common.py` | Add CHANNEL_LINK_HEADER OpenAPI parameter |
| `tests/base.py` | Add create_channel, create_channel_link, create_order helpers |
| `requirements.txt` | Add celery, redis, django-celery-beat |
| `docker-compose.yml` | Add Redis service |

---

## Async Infrastructure

- **Celery** with Redis broker for async task processing
- **Webhook dispatch** runs as Celery task with exponential backoff retry (max 5 attempts)
- **Periodic health check** task flags channel links that haven't synced in 24+ hours

---

## Verification

1. Run existing tests: `pytest -s` — all must pass (backward compat)
2. Run new tests: `pytest tests/channels/ tests/integrations/ tests/orders/ tests/webhooks/ -s`
3. Manual flow test:
   - Create channel link (internal_pos + location)
   - Create order via POST /api/v1/orders/ with items
   - Transition status: RECEIVED → ACCEPTED → PREPARING → READY → COMPLETED
   - Verify OrderStatusLog records each transition
   - Verify invalid transition (RECEIVED → DELIVERED) returns 400
4. Adapter test: `AdapterRegistry.get_adapter(channel_link)` returns InternalPOSAdapter instance
5. Canonical test: Create product, build CanonicalMenu.from_product_queryset(), verify output matches

---

## Design Principles

1. **Your POS is just another adapter** — `InternalPOSAdapter` implements the same interface as `UberEatsAdapter`
2. **Canonical data layer** — all data flows through standardized dataclasses
3. **Tenant isolation** — orders, links, configs, webhooks all scoped to tenant schema
4. **State machine enforcement** — invalid order transitions return 400
5. **Snapshot pattern** — order items store PLU/name/price at time of order (not FK-dependent)
6. **Signature verification** — inbound webhooks verified by adapter before processing
7. **Schema resolution** — inbound webhooks auto-resolve tenant from ChannelLink UUID

---

## Implementation Status

| Phase | Status | Notes |
|---|---|---|
| Phase 1: channels + integrations | **DONE** | All models, adapters, canonical dataclasses, views, tests |
| Phase 2: orders | **DONE** | Order CRUD, state machine, OrderService, status transitions |
| Phase 3: channel data migration | **NOT STARTED** | Dual-write migration from ProductLocation.channels JSONField |
| Phase 4: webhooks | **DONE** | Inbound/outbound, HMAC verification, tenant resolution |
| Phase 5: async infrastructure | **DONE** | Celery + Redis config, async dispatch task, health check task |
| Phase 6: tests | **DONE** | 95 tests passing (8 existing + 87 new) |
