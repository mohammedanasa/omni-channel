# Change 001: Integration Framework Implementation

**Date:** 2026-03-05
**Status:** Complete
**Tests:** 95 passed (8 existing + 87 new)

---

## Summary

Implemented a hub-and-spoke integration framework with 4 new Django apps, adapter architecture, canonical data layer, order management with state machine, and webhook infrastructure.

---

## New Apps Created

### 1. `channels` (SHARED app)

**Purpose:** Global registry of available channel/integration types.

| File | Description |
|---|---|
| `channels/models.py` | `Channel` model with slug, type, direction, adapter_class, config_schema |
| `channels/serializers.py` | `ChannelSerializer` (ModelSerializer) |
| `channels/views.py` | `ChannelViewSet` (read-only: list + retrieve) |
| `channels/urls.py` | Router: `channels/` |
| `channels/admin.py` | Admin registration with filters |
| `channels/apps.py` | AppConfig |

### 2. `integrations` (TENANT app)

**Purpose:** Channel links, product channel configs, adapter framework, canonical data layer.

| File | Description |
|---|---|
| `integrations/models.py` | `ChannelLink` (FK→Channel + FK→Location, credentials, sync status), `ProductChannelConfig` (FK→ProductLocation + FK→Channel, price override, availability) |
| `integrations/serializers.py` | `ChannelLinkSerializer`, `ProductChannelConfigSerializer` |
| `integrations/views.py` | `ChannelLinkViewSet` (CRUD + `validate` + `sync_menu` actions), `ProductChannelConfigViewSet` |
| `integrations/urls.py` | Router: `channel-links/`, `product-channel-configs/` |
| `integrations/admin.py` | Admin registrations |
| `integrations/apps.py` | AppConfig |
| `integrations/adapters/__init__.py` | `AdapterRegistry` — import, cache, validate, instantiate adapters by dotted path |
| `integrations/adapters/base.py` | `AbstractChannelAdapter` ABC with 8 abstract methods + 2 optional hooks |
| `integrations/adapters/internal.py` | `InternalPOSAdapter` — internal POS adapter (DB is source of truth, most methods are no-ops) |
| `integrations/canonical/__init__.py` | Package init |
| `integrations/canonical/menu.py` | `CanonicalModifier`, `CanonicalModifierGroup`, `CanonicalProduct`, `CanonicalMenu` dataclasses + `from_product_queryset()` builder |
| `integrations/canonical/orders.py` | `CanonicalOrderModifier`, `CanonicalOrderItem` (with `total_price` property), `CanonicalOrder` (with `from_dict()` + `to_order_kwargs()`) |
| `integrations/canonical/results.py` | `SyncResult`, `WebhookResult` dataclasses |

### 3. `orders` (TENANT app)

**Purpose:** Order management with state machine, service layer, status logging.

| File | Description |
|---|---|
| `orders/models.py` | `Order` (with status/type enums, financial fields, timing fields, indexes), `OrderItem` (snapshot fields), `OrderModifier`, `OrderStatusLog`, `VALID_TRANSITIONS` state machine dict |
| `orders/services.py` | `OrderService` — `create_order_from_canonical()` (atomic), `transition_status()` (validates transitions, sets timestamps, creates log), `_generate_order_number()` |
| `orders/serializers.py` | `OrderListSerializer`, `OrderDetailSerializer` (nested items + logs), `OrderCreateSerializer`, `OrderStatusUpdateSerializer` |
| `orders/views.py` | `OrderViewSet` (CRUD + `update_status` action, location filtering via X-Location-ID) |
| `orders/urls.py` | Router: `orders/` |
| `orders/admin.py` | Admin with inlines for items and status logs |
| `orders/apps.py` | AppConfig |

### 4. `webhooks` (TENANT app)

**Purpose:** Inbound webhook receiving, outbound webhook dispatch, logging.

| File | Description |
|---|---|
| `webhooks/models.py` | `WebhookEndpoint` (url, secret, events, is_active), `WebhookLog` (direction, channel_slug, event_type, request/response data, success, retries) |
| `webhooks/verification.py` | `generate_hmac_signature()`, `verify_hmac_signature()` using HMAC-SHA256 |
| `webhooks/dispatcher.py` | `dispatch_webhook_event()` — sends to all subscribed active endpoints with HMAC signing |
| `webhooks/serializers.py` | `WebhookEndpointSerializer` (secret is write-only), `WebhookLogSerializer` (read-only) |
| `webhooks/views.py` | `WebhookEndpointViewSet`, `WebhookLogViewSet` (read-only), `InboundWebhookView` (CSRF-exempt, resolves tenant from ChannelLink UUID, verifies signature via adapter) |
| `webhooks/urls.py` | Router: `webhooks/endpoints/`, `webhooks/logs/`, plus path `webhooks/inbound/<uuid>/` |
| `webhooks/admin.py` | Admin registrations |
| `webhooks/tasks.py` | Celery tasks: `dispatch_webhook_async` (with exponential backoff retry), `check_sync_health` (periodic stale link detection) |
| `webhooks/apps.py` | AppConfig |

---

## Async Infrastructure (Celery + Redis)

| File | Description |
|---|---|
| `backend/celery.py` | Celery app config with autodiscover |
| `backend/__init__.py` | Conditional celery import (graceful if celery not installed) |

---

## Modified Existing Files

### `backend/settings.py`
- Added `channels` to `SHARED_APPS`
- Added `integrations`, `orders`, `webhooks` to `TENANT_APPS`
- Added Celery configuration (broker URL, result backend, serializer settings)

### `backend/api_v1_urls.py`
- Added 4 new URL includes: `channels.urls`, `integrations.urls`, `orders.urls`, `webhooks.urls`

### `accounts/middleware.py`
- Added to `TENANT_ONLY_PREFIXES`: `/api/v1/channel-links/`, `/api/v1/product-channel-configs/`, `/api/v1/orders/`, `/api/v1/webhooks/endpoints/`, `/api/v1/webhooks/logs/`
- Added new `TENANT_EXEMPT_PREFIXES`: `/api/v1/webhooks/inbound/` (tenant resolved from ChannelLink)
- Updated `_requires_tenant()` to check exempt prefixes first

### `helpers/common.py`
- Added `CHANNEL_LINK_HEADER` OpenAPI parameter

### `tests/base.py`
- Added `create_channel()` helper — creates/gets Channel via ORM
- Added `create_channel_link()` helper — creates ChannelLink via API
- Added `create_order()` helper — creates Order via API

### `requirements.txt`
- Added `celery==5.4.0`, `redis==5.2.1`, `django-celery-beat==2.7.0`

### `docker-compose.yml`
- Added `redis` service (redis:7-alpine on port 6379)

---

## Tests Created

### `tests/channels/test_channel_crud.py` (5 tests)
- List channels (authenticated)
- List channels (unauthenticated → 401)
- Retrieve single channel
- Channels are read-only (POST → 405)
- Inactive channels hidden from list

### `tests/integrations/test_channel_link_crud.py` (6 tests)
- Create channel link
- List channel links
- Requires tenant header (→ 400)
- Unique constraint on (channel, location)
- Validate credentials action
- Tenant isolation (A can't see B's links)

### `tests/integrations/test_adapter_registry.py` (5 tests)
- Get adapter class (valid path)
- Caching behavior
- Invalid path raises ImportError/AttributeError
- Non-subclass raises TypeError
- Clear cache

### `tests/integrations/test_internal_adapter.py` (6 tests)
- push_menu returns success no-op
- validate_credentials always True
- verify_webhook_signature always True
- handle_webhook returns no-op
- update_order_status always True
- normalize_inbound_order builds CanonicalOrder

### `tests/integrations/test_canonical_models.py` (7 tests)
- CanonicalProduct to_dict
- CanonicalMenu to_dict
- Modifier group nesting
- OrderItem total_price calculation
- from_dict round-trip preserves all fields
- to_dict includes computed total_price
- SyncResult and WebhookResult to_dict

### `tests/integrations/test_product_channel_config.py` (1 test)
- Create ProductChannelConfig via API with proper tenant context

### `tests/orders/test_order_crud.py` (5 tests)
- Create order (returns ORD-xxx number)
- List orders
- Retrieve order detail (includes items + status_logs)
- Requires tenant header
- Tenant isolation

### `tests/orders/test_order_service.py` (1 test)
- Create order from CanonicalOrder (atomic, items + modifiers + status log)

### `tests/orders/test_order_state_machine.py` (7 tests)
- Valid transition: received → accepted
- Full happy path: received → accepted → preparing → ready → completed
- Invalid transition: received → delivered (→ 400)
- Terminal state: completed → anything (→ 400)
- Rejection from received
- Status logs recorded on each transition
- Timestamp set on accepted

### `tests/webhooks/test_inbound_webhook.py` (2 tests)
- Inbound webhook resolves tenant from ChannelLink UUID
- Invalid link ID returns 404

### `tests/webhooks/test_outbound_dispatch.py` (5 tests)
- Dispatch success (mocked HTTP)
- Skips unsubscribed events
- Includes HMAC signature
- Handles connection failure gracefully
- Wildcard event subscription

---

## New API Endpoints

| Endpoint | Method | Tenant | Description |
|---|---|---|---|
| `channels/` | GET | No | List active channels |
| `channels/{id}/` | GET | No | Channel detail |
| `channel-links/` | GET/POST | Yes | List/create links |
| `channel-links/{id}/` | GET/PUT/PATCH/DELETE | Yes | Manage link |
| `channel-links/{id}/validate/` | POST | Yes | Test credentials |
| `channel-links/{id}/sync_menu/` | POST | Yes | Push menu |
| `product-channel-configs/` | CRUD | Yes | Channel product config |
| `orders/` | GET/POST | Yes | List/create orders |
| `orders/{id}/` | GET | Yes | Order detail |
| `orders/{id}/status/` | PATCH | Yes | Transition status |
| `webhooks/endpoints/` | CRUD | Yes | Outbound webhook config |
| `webhooks/logs/` | GET | Yes | View logs |
| `webhooks/inbound/{link_id}/` | POST | Auto | Inbound receiver |

---

## Key Design Decisions

1. **channels vs integrations split** — django-tenants requires all models in an app to be either SHARED or TENANT. Channel definitions are global (SHARED), but links/configs are per-tenant (TENANT).

2. **Snapshot pattern for orders** — OrderItem stores `plu`, `name`, `unit_price` as snapshots rather than relying solely on FK. Product FK is SET_NULL so orders survive product deletion.

3. **Adapter registry with caching** — `AdapterRegistry` imports adapter classes lazily and caches them. Validates they're subclasses of `AbstractChannelAdapter`.

4. **Inbound webhook tenant resolution** — iterates tenant schemas to find the ChannelLink by UUID, then stays on that schema for processing. No JWT auth needed — uses adapter-level signature verification.

5. **Celery import is conditional** — `backend/__init__.py` wraps the celery import in try/except so the project works without celery installed.
