# CLAUDE.md — Omnichannel POS & Order Management Hub

## Project Summary

A **multi-tenant Django REST API** for managing Point of Sale (POS) operations and aggregating orders from online channels (UberEats, DoorDash, etc.). Each merchant (tenant) is isolated into its own PostgreSQL schema via `django-tenants`. The API uses JWT authentication (via Djoser + SimpleJWT), DRF ViewSets, and OpenAPI docs via `drf-spectacular`.

---

## Tech Stack

| Layer              | Technology                                       |
| ------------------ | ------------------------------------------------ |
| Framework          | Django 5.2 + Django REST Framework 3.16          |
| Multi-Tenancy      | `django-tenants` 3.9 (schema-per-tenant)         |
| Auth               | `djoser` 2.3 + `djangorestframework-simplejwt`   |
| Database           | PostgreSQL (via `psycopg2-binary`)                |
| API Docs           | `drf-spectacular` (Swagger + ReDoc)               |
| Config             | `python-decouple` (`.env` file)                   |
| Task Queue         | Celery + Redis                                    |
| Testing            | `pytest` + `pytest-django` + `model-bakery`       |
| Python             | 3.12                                              |

---

## Architecture: Modular Monolith + Service Layer

This project follows a **Modular Monolith** pattern with a **Service Layer** for business logic separation. Each Django app is a self-contained module with clear internal structure and boundaries.

### Layer Responsibilities

```
View       → HTTP in/out, header parsing, permissions, Response()
  ↓ calls
Service    → Business logic, multi-model orchestration, @transaction.atomic
  ↓ uses
Model      → Data integrity (clean/save), field defaults, single-table queries
Serializer → Input validation, field-level rules, representation formatting
```

### Rules

1. **Views never contain business logic.** Views parse the request, call a service, and return the response. Views own: header extraction, query param parsing, serializer selection, permission checks, OpenAPI decorators, `Response()` construction.
2. **Services own business logic.** Any operation that spans multiple models, enforces business rules, or orchestrates a workflow belongs in a service. Services are plain Python classes with `@staticmethod` or `@classmethod` methods. Services use `@transaction.atomic` when they modify multiple models.
3. **Models own data integrity.** Validation constraints (`clean()`), auto-generated fields (`save()`), and single-table utility methods stay in models. Models never import from views or services.
4. **Serializers own shape validation.** Input/output field mapping, nested representation, field-level validation. Serializers should not contain multi-model orchestration — that belongs in services.
5. **No circular imports between apps.** Use string references for ForeignKeys across apps (e.g., `'locations.Location'`). Use lazy imports inside methods when needed to avoid circular dependencies within a split models package.
6. **Re-export via `__init__.py`.** When a module is split into a package, the `__init__.py` must re-export all public names so external imports remain unchanged.
7. **Migrations must resolve.** Everything referenced by migrations (models, managers, custom fields) must be importable from the original module path via `__init__.py` re-exports.
8. **Shared utilities go in `common/`.** Base models (`BaseUUIDModel`), shared constants (`INTERNAL_POS_SLUG`), shared mixins, and cross-app utilities live in the `common` app.
9. **`@extend_schema_field` on every `SerializerMethodField`.** All `get_*` methods on serializers must have a `drf-spectacular` type annotation to avoid schema generation warnings.

### When to Split a File vs Keep It Flat

| File size          | Action                                                          |
| ------------------ | --------------------------------------------------------------- |
| < 300 lines        | **Stay flat** — single `models.py`, `views.py`, etc.            |
| 300–800 lines      | **Split selectively** — only split the oversized file           |
| 800+ lines         | **Full package split** — `models/`, `services/`, `serializers/`, `views/` |

---

## Settings Structure

Settings are split into environment-specific files:

```
backend/settings/
├── __init__.py       # Auto-selects based on DJANGO_ENV env var (default: development)
├── base.py           # All shared configuration
├── development.py    # DEBUG=True, console email, relaxed tokens, ALLOWED_HOSTS=*
└── production.py     # DEBUG=False, SSL/HSTS hardening, required SECRET_KEY, tighter tokens
```

Set `DJANGO_ENV=production` for production. All `DJANGO_SETTINGS_MODULE = backend.settings` references work unchanged.

---

## Project Structure

```
django-auth/                        # Root
├── backend/                        # Django project package
│   ├── settings/                   # Split settings (base, development, production)
│   │   ├── __init__.py             # Env-based auto-selection
│   │   ├── base.py                 # Shared settings
│   │   ├── development.py          # Dev overrides
│   │   └── production.py           # Prod hardening
│   ├── urls.py                     # Root URL config → /api/v1/
│   ├── api_v1_urls.py              # V1 sub-router
│   ├── celery.py                   # Celery app config
│   ├── asgi.py / wsgi.py
│   └── __init__.py
│
├── common/                         # Shared utilities (NOT a Django app in INSTALLED_APPS)
│   ├── __init__.py
│   ├── constants.py                # INTERNAL_POS_SLUG and shared constants
│   └── models.py                   # BaseUUIDModel (abstract UUID primary key)
│
├── accounts/                       # SHARED app — Users, Merchants, Domains
│   ├── models/
│   │   ├── __init__.py             # Re-exports: User, UserManager, Merchant, Domain
│   │   ├── user.py                 # User (custom, email-based) + UserManager
│   │   ├── merchant.py             # Merchant (TenantMixin)
│   │   └── domain.py               # Domain (DomainMixin)
│   ├── serializers/
│   │   ├── __init__.py             # Re-exports all serializers
│   │   ├── user.py                 # UserCreateSerializer
│   │   └── merchant.py             # MerchantSerializer, MerchantCreate/Update
│   ├── views.py                    # MerchantViewSet
│   ├── permissions.py              # IsMerchantOwner
│   ├── middleware.py               # TenantFromHeaderMiddleware
│   ├── urls.py
│   └── admin.py
│
├── locations/                      # TENANT app — Physical store locations
│   ├── models/
│   │   ├── __init__.py             # Re-exports: Location
│   │   └── location.py             # Location model
│   ├── serializers/
│   ├── views/
│   ├── urls.py
│   └── admin.py
│
├── products/                       # TENANT app — Products, Categories, Tax Rates
│   ├── models/
│   │   ├── __init__.py             # Re-exports: Product, Category, TaxRate, ProductLocation, ProductRelation
│   │   ├── tax_rate.py             # TaxRate (percentage/flat-fee, auto-switch default)
│   │   ├── category.py             # Category (pos_category_id, sort_order)
│   │   ├── product.py              # Product + ProductType enum
│   │   ├── product_location.py     # ProductLocation junction
│   │   └── product_relation.py     # ProductRelation parent-child
│   ├── serializers/
│   │   ├── __init__.py             # Re-exports all serializers
│   │   ├── product.py              # ProductSerializer, NestedProductSerializer
│   │   ├── category.py             # CategorySerializer
│   │   ├── tax_rate.py             # TaxRateSerializer
│   │   ├── bulk_product_sync.py    # BulkProductSyncSerializer
│   │   └── location_assignment.py  # LocationAssignment serializers
│   ├── services/
│   │   ├── __init__.py             # Re-exports: MenuService, AvailabilityService, PricingService, ProductService
│   │   ├── menu.py                 # MenuService — export_menu()
│   │   ├── availability.py         # AvailabilityService — mark_unavailable() (3-scope)
│   │   ├── pricing.py              # PricingService — update_location_pricing()
│   │   └── product.py              # ProductService — auto_assign_location(), bulk_delete()
│   ├── views/
│   │   ├── __init__.py             # Re-exports: ProductViewSet, CategoryViewSet, TaxRateViewSet
│   │   ├── mixins.py               # HeaderContextMixin, CatalogWriteProtectionMixin
│   │   ├── constants.py            # CHANNEL_HEADER, PRODUCT_TYPE_FILTER (OpenAPI params)
│   │   ├── product.py              # ProductViewSet (thin — delegates to services)
│   │   ├── category.py             # CategoryViewSet
│   │   └── tax_rate.py             # TaxRateViewSet
│   ├── urls.py
│   └── admin.py
│
├── channels/                       # SHARED app — Channel definitions (global)
│   ├── models.py                   # Channel (slug, channel_type, direction, adapter_class) + ChannelType, ChannelDirection enums
│   ├── views.py                    # ChannelViewSet (read-only)
│   ├── urls.py
│   └── admin.py
│
├── integrations/                   # TENANT app — Channel links, adapters, canonical data
│   ├── models.py                   # ChannelLink (single POS per location enforcement), ProductChannelConfig (write-through)
│   ├── services.py                 # IntegrationSyncService (pull_and_persist, push_to_active_channels)
│   ├── signals.py                  # Product mutation signals → outbound channel sync
│   ├── adapters/
│   │   ├── __init__.py             # AdapterRegistry (dynamic loading + cache)
│   │   ├── base.py                 # AbstractChannelAdapter interface (incl. handle_menu_webhook)
│   │   ├── internal.py             # InternalPOSAdapter (DB as source of truth)
│   │   └── deliveroo.py            # DeliverooAdapter (OAuth2, menu sync, orders, webhooks)
│   ├── canonical/
│   │   ├── menu.py                 # CanonicalMenu, CanonicalProduct, CanonicalModifierGroup
│   │   ├── orders.py               # CanonicalOrder, CanonicalOrderItem
│   │   └── results.py              # SyncResult, WebhookResult
│   ├── views.py                    # ChannelLinkViewSet (sync_menu, pull_menu, validate), ProductChannelConfigViewSet
│   ├── serializers.py
│   ├── urls.py
│   └── admin.py
│
├── orders/                         # TENANT app — Order processing
│   ├── models.py                   # Order, OrderItem, OrderModifier, OrderStatusLog
│   ├── services.py                 # OrderService (create_order_from_canonical, transition_status)
│   ├── views.py                    # OrderViewSet (status action)
│   ├── urls.py
│   └── admin.py
│
├── menus/                          # TENANT app — Multi-location menu curation & publishing
│   ├── models/
│   │   ├── __init__.py             # Re-exports all models
│   │   ├── menu.py                 # Menu (merchant-level)
│   │   ├── menu_category.py        # MenuCategory (customer-facing grouping)
│   │   ├── menu_item.py            # MenuItem (product reference + price override)
│   │   ├── menu_availability.py    # MenuAvailability (daypart windows)
│   │   ├── menu_location.py        # MenuLocation (assigns menu to locations)
│   │   └── menu_location_channel.py # MenuLocationChannel (publish state per channel)
│   ├── services/
│   │   ├── __init__.py             # Re-exports: MenuBuilderService, MenuPublisherService
│   │   ├── menu_builder.py         # Duplicate menus, assign locations/channels
│   │   └── menu_publisher.py       # Build payload (READ catalog), push via adapter
│   ├── serializers/
│   ├── views/
│   │   └── menu.py                 # MenuViewSet (nested actions for categories, items, locations, channels, publish)
│   ├── urls.py
│   └── admin.py
│
├── webhooks/                       # TENANT app — Inbound/outbound webhook system
│   ├── models.py                   # WebhookEndpoint, WebhookLog
│   ├── views.py                    # WebhookEndpointViewSet, WebhookLogViewSet, InboundWebhookView
│   ├── dispatcher.py               # dispatch_webhook_event() (outbound)
│   ├── verification.py             # HMAC-SHA256 signing/verification
│   ├── urls.py
│   └── admin.py
│
├── helpers/
│   ├── common.py                   # OpenAPI helpers (TENANT_HEADER, LOCATION_HEADER, @tenant_schema)
│   └── permissions/
│       └── permissions.py          # HasTenantAccess permission
│
├── tests/
│   ├── base.py                     # BaseAPITest (create_user, authenticate, create_merchant, etc.)
│   ├── merchants/test_merchants.py
│   ├── locations/test_locations.py
│   ├── products/test_products.py
│   └── menus/test_menus.py
│
├── docs/
│   ├── channel-integration.md      # Channel adapter architecture guide
│   └── menu.md                     # Multi-location menu system design doc
│
├── manage.py
├── requirements.txt
├── pytest.ini
├── docker-compose.yml              # Postgres container (port 5434:5432)
├── schema.yml                      # Generated OpenAPI schema
├── .env                            # Local env config
└── .gitignore
```

---

## Django Apps & Tenancy

| App            | Type     | Description                                              |
| -------------- | -------- | -------------------------------------------------------- |
| `accounts`     | SHARED   | Lives in **public** schema. Custom User, Merchant, Domain models. |
| `channels`     | SHARED   | Lives in **public** schema. Global channel definitions (UberEats, DoorDash, etc.). |
| `locations`    | TENANT   | Lives in **per-tenant** schemas. Physical store locations. |
| `products`     | TENANT   | Lives in **per-tenant** schemas. Products, Categories, Tax Rates, Product-Location assignments. |
| `integrations` | TENANT   | Lives in **per-tenant** schemas. ChannelLinks, ProductChannelConfigs, adapters. |
| `orders`       | TENANT   | Lives in **per-tenant** schemas. Orders, OrderItems, OrderModifiers, status logs. |
| `menus`        | TENANT   | Lives in **per-tenant** schemas. Menus, categories, items, locations, publish state. |
| `webhooks`     | TENANT   | Lives in **per-tenant** schemas. Webhook endpoints, logs, inbound handler. |
| `common`       | UTILITY  | Not in INSTALLED_APPS. Shared abstract models (BaseUUIDModel). |

**Tenant model:** `accounts.Merchant` (extends `TenantMixin`)
**Domain model:** `accounts.Domain` (extends `DomainMixin`)

---

## Key Architectural Patterns

### Multi-Tenancy via Header (not subdomain)
- `TENANT_SUBDOMAIN_BASED_ROUTING = False`
- Custom middleware `accounts.middleware.TenantFromHeaderMiddleware` reads `X-Tenant-ID` header
- Tenant-only prefixes: `/products/`, `/categories/`, `/tax-rates/`, `/locations/`, `/channel-links/`, `/product-channel-configs/`, `/orders/`, `/webhooks/endpoints/`, `/webhooks/logs/`, `/menus/`
- Public-schema routes (auth, merchants, channels) work without the header
- Tenant-exempt routes: `/webhooks/inbound/` (resolves tenant from ChannelLink)

### Authentication Flow
1. Register: `POST /api/v1/auth/users/` (Djoser)
2. Login: `POST /api/v1/auth/jwt/create/` → returns `access` + `refresh` tokens
3. All subsequent requests: `Authorization: Bearer <access_token>`

### Custom Headers
| Header             | Purpose                                      | Required |
| ------------------ | -------------------------------------------- | -------- |
| `Authorization`    | JWT Bearer token                             | Yes      |
| `X-Tenant-ID`     | Merchant UUID → switches DB schema           | For tenant endpoints |
| `X-Location-ID`   | Location UUID → scopes/filters by location   | Optional |
| `X-Channel`        | Channel name (e.g. `ubereats`, `doordash`)  | Optional |
| `X-Channel-Link-ID`| ChannelLink UUID for channel-specific ops   | Optional |

### Product Types (enum)
| Value | Type           | Description                              |
| ----- | -------------- | ---------------------------------------- |
| 1     | MAIN           | Sellable products (burgers, drinks)      |
| 2     | MODIFIER_ITEM  | Individual options (lettuce, cheese)     |
| 3     | MODIFIER_GROUP | Container for modifier items             |
| 4     | BUNDLE_GROUP   | Container for bundle options (combos)    |

### Pricing Resolution (5-level fallback)
1. MenuItem.price_override → Menu-specific price
2. ProductChannelConfig.price → Product + channel config (writes through to #3 on save)
3. ProductLocation.channels[ch]["price"] → Channel price at location (single source of truth)
4. ProductLocation.price_override → Location base price
5. Product.price → Catalog base price

### Channel Pricing: Single Source of Truth
`ProductLocation.channels` JSONField is the canonical source for channel-specific pricing and availability. `ProductChannelConfig` is the admin/API-facing model — on save, it writes through to the JSONField via `_sync_to_product_location()`. On delete, it removes the channel entry from the JSONField. This eliminates the dual-source-of-truth problem.

### Availability Resolution (3-scope)
1. Product.visible = False → Global (all locations, all channels)
2. ProductLocation.is_available = False → Location-wide
3. ProductLocation.channels[ch]["is_available"] = False → Channel-specific at location

### Tax Resolution (3-tier)
1. ProductLocation tax override → Location-specific
2. Product tax rate → Product default
3. TaxRate.is_default = True → Merchant default

### Menu Publishing (READ catalog, WRITE external)
- Publishing does NOT modify catalog data (Product, ProductLocation)
- Builds payload from catalog, pushes via adapter, stores snapshot
- Each location+channel gets an independent publish with resolved prices

### Adapter Pattern (Hub-and-Spoke)
- All external systems connect via `AbstractChannelAdapter`
- Internal POS is just another adapter (database as source of truth)
- `AdapterRegistry` dynamically loads and caches adapter classes
- Adapters handle both order and menu webhook events (see `handle_webhook` + `handle_menu_webhook`)

### Integration Sync (Pull & Push)
- **Pull (inbound):** `POST /channel-links/{id}/pull_menu/` → `IntegrationSyncService.pull_and_persist()` calls `adapter.pull_menu()`, converts `CanonicalMenu` → upserts products/categories/modifiers, assigns to location with channel-specific pricing
- **Push (outbound):** `POST /channel-links/{id}/sync_menu/` → builds `CanonicalMenu` from local DB, calls `adapter.push_menu()`
- **Auto-push on product change:** Django signals on `ProductLocation` save/delete trigger `IntegrationSyncService.push_to_active_channels()` to sync all active non-POS channel links for the affected location. POS-type channels are skipped (catalog push to POS reverses the intended data flow).
- **Webhook-triggered sync:** Inbound `menu.*`/`item.*` events route through `adapter.handle_menu_webhook()` — can trigger `pull_and_persist()` or directly update availability

### Catalog Ownership (POS-as-Master)
The system enforces a **single active POS per location** with per-product write protection.

**Per-Location POS:**
- Each location can have at most one active POS-type (`channel_type="pos"`) ChannelLink.
- Different locations under the same merchant can use different POS systems (e.g. Location A → Clover, Location B → Square, Location C → internal).
- `ChannelLink.save()` enforces this constraint. Marketplace/direct channels are unlimited.
- POS ownership is derived from ChannelLinks — there is no merchant-level `catalog_source` field.

**Per-Product Write Protection (CatalogWriteProtectionMixin):**
- Write protection is based on `Product.managed_by`, not merchant-level state.
- Products with `managed_by="internal_pos"` (platform-owned, locally created or seeded from marketplace) are **fully writable**.
- Products with `managed_by="clover"` (or any external POS slug) have core catalog fields **read-only** (name, price, description, product_type, categories, etc.).
- Empty string `managed_by=""` is legacy/transitional — treated the same as `"internal_pos"` for write protection (fully writable).
- `POST /products/` (create) is **always allowed** — new products are platform-owned (`managed_by="internal_pos"`).
- `DELETE` and `PATCH/PUT` on protected fields return 403: _"This product is managed by {managed_by}."_
- **Always allowed** regardless of `managed_by`: `update_location_pricing`, `mark_unavailable`, channel pricing overrides, menu curation, menu publishing.
- `bulk_delete` checks per-product: blocks only external POS-managed products, allows platform-owned ones.

**Product Origin Tracking:**
- `Product.managed_by` field tracks catalog ownership. `INTERNAL_POS_SLUG` constant lives in `common/constants.py`.
- `"internal_pos"` = platform-owned (created locally via API OR seeded from marketplace pulls like UberEats/DoorDash).
- External POS slug (e.g. `"clover"`, `"square"`) = imported from that POS, external POS owns core catalog fields.
- `""` (empty) = legacy/transitional, treated same as `"internal_pos"` for write protection.
- **Ownership precedence:** external POS > `"internal_pos"` > `""` (never downgrade). A product already owned by an external POS will not be overwritten to `"internal_pos"` by a marketplace pull.
- Stamped automatically by `IntegrationSyncService.pull_and_persist()` on all products, modifier groups, and modifier items.
- **Marketplace pulls** (UberEats, DoorDash) seed products as `managed_by="internal_pos"` — the platform becomes source of truth.
- **POS pulls** (Clover, Square) stamp the POS slug (e.g. `managed_by="clover"`) — the external POS owns the catalog.
- Read-only via API (`ProductSerializer`).

**Data Flow:**
```
External POS (Clover/Square) ──pull_menu──> Our Platform ──publish──> Delivery Channels
       owns: product catalog          owns: overrides, menus      receives: curated menus
       managed_by="clover"            managed_by="internal_pos"

Marketplace (UberEats/DoorDash) ──pull_menu──> Our Platform (seeds products)
       source of initial data              becomes owner: managed_by="internal_pos"
```

---

## API Endpoints (v1)

All under `/api/v1/`:

### Auth (Djoser)
- `POST auth/users/` — Register
- `POST auth/jwt/create/` — Login (get tokens)
- `POST auth/jwt/refresh/` — Refresh token

### Merchants (public schema)
- `GET/POST merchants/`
- `GET/PUT/PATCH/DELETE merchants/{id}/`

### Channels (public schema, read-only)
- `GET channels/`
- `GET channels/{id}/`

### Locations (tenant schema — requires `X-Tenant-ID`)
- `GET/POST locations/`
- `GET/PUT/PATCH/DELETE locations/{id}/`

### Products (tenant schema — requires `X-Tenant-ID`)
- `GET/POST products/` — List/Create (filters: `product_type`, `category_id`, `visible`, `is_available`, `is_active`, `search`). **Create always allowed** (new products are `managed_by="internal_pos"`).
- `GET/PUT/PATCH/DELETE products/{plu}/` — By PLU lookup. **Write/delete blocked on external POS-managed products** (checks `Product.managed_by`).
- `POST products/bulk_sync/` — Bulk upsert.
- `GET products/export_menu/` — Export menu (requires `X-Location-ID`)
- `POST products/mark_unavailable/` — Mark products unavailable (3-scope). **Always allowed.**
- `PATCH products/{plu}/update_location_pricing/` — Update location pricing (requires `X-Location-ID`). **Always allowed.**
- `POST products/bulk_delete/` — Bulk delete by PLUs. **Blocks external POS-managed products per-product.**

### Categories (tenant schema)
- `GET/POST categories/`
- `GET/PUT/PATCH/DELETE categories/{pos_category_id}/`

### Tax Rates (tenant schema)
- `GET/POST tax-rates/`
- `GET/PUT/PATCH/DELETE tax-rates/{id}/`

### Channel Links (tenant schema)
- `GET/POST channel-links/`
- `GET/PUT/PATCH/DELETE channel-links/{id}/`
- `POST channel-links/{id}/validate/` — Validate credentials
- `POST channel-links/{id}/sync_menu/` — Push menu to channel (outbound)
- `POST channel-links/{id}/pull_menu/` — Pull menu from channel and persist locally (inbound)

### Product Channel Configs (tenant schema)
- `GET/POST product-channel-configs/`
- `GET/PUT/PATCH/DELETE product-channel-configs/{id}/`

### Orders (tenant schema)
- `GET/POST orders/`
- `GET/PUT/PATCH/DELETE orders/{id}/`
- `PATCH orders/{id}/status/` — Update order status

### Menus (tenant schema)
- `GET/POST menus/` — List/Create menus (GET returns nested categories, items, availabilities, locations with channels)
- `GET/PATCH/DELETE menus/{id}/` — Menu detail (GET returns full nested response)
- `POST menus/{id}/categories/` — Add category
- `PATCH/DELETE menus/{id}/categories/{cat_id}/` — Update/delete category
- `POST menus/{id}/items/` — Add item
- `PATCH/DELETE menus/{id}/items/{item_id}/` — Update/delete item
- `PATCH menus/{id}/items/bulk/` — Bulk update items (sort_order, price_override, is_visible, menu_category)
- `POST menus/{id}/items/bulk-remove/` — Bulk remove items
- `PATCH menus/{id}/categories/bulk/` — Bulk update categories (sort_order, name, description, image_url)
- `POST menus/{id}/availabilities/` — Add availability window
- `DELETE menus/{id}/availabilities/{avail_id}/` — Remove availability
- `POST/DELETE menus/{id}/locations/` — Assign/remove location (uses `X-Location-ID` header)
- `POST/DELETE menus/{id}/channels/` — Assign/remove channel (uses `X-Location-ID` + `X-Channel-Link-ID` headers)
- `POST menus/{id}/publish/` — Publish to all assigned location-channels
- `GET menus/{id}/publish-status/` — Get publish state
- `POST menus/{id}/duplicate/` — Clone menu

### Webhooks (tenant schema)
- `GET/POST webhooks/endpoints/` — Manage webhook endpoints
- `GET/PUT/PATCH/DELETE webhooks/endpoints/{id}/`
- `GET webhooks/logs/` — View webhook logs (read-only)
- `GET webhooks/logs/{id}/`
- `POST webhooks/inbound/{channel_link_id}/` — Receive inbound webhook (no auth, signature-verified). Handles order events (`orders.*`) and menu/item events (`menu.*`, `item.*`)

### API Docs
- `GET /api/v1/schema/` — OpenAPI JSON
- `GET /api/v1/docs/` — Swagger UI
- `GET /api/v1/redoc/` — ReDoc

---

## Adding a New App — Checklist

When creating a new Django app, follow this structure:

```
myapp/
├── models/
│   ├── __init__.py        # from .foo import Foo; __all__ = ["Foo"]
│   └── foo.py             # class Foo(BaseUUIDModel): ...
├── serializers/
│   ├── __init__.py        # from .foo import FooSerializer; __all__ = [...]
│   └── foo.py
├── services/
│   ├── __init__.py        # from .foo import FooService; __all__ = [...]
│   └── foo.py             # class FooService: @staticmethod def do_thing(): ...
├── views/
│   ├── __init__.py        # from .foo import FooViewSet; __all__ = [...]
│   └── foo.py             # class FooViewSet(viewsets.ModelViewSet): ...
├── urls.py
├── admin.py
└── apps.py
```

1. Models inherit from `common.models.BaseUUIDModel`
2. Register app in `backend/settings/base.py` under `SHARED_APPS` or `TENANT_APPS`
3. Add URL include in `backend/api_v1_urls.py`
4. Add tenant-only prefixes in `accounts/middleware.py` if it's a TENANT app
5. Run `python manage.py makemigrations <appname>`
6. Run `python manage.py migrate_schemas`
7. Add tests in `tests/<appname>/`

---

## Development Commands

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database
```bash
python manage.py makemigrations
python manage.py migrate_schemas --shared    # Public schema only
python manage.py migrate_schemas --tenant    # All tenant schemas
python manage.py migrate_schemas             # Everything
```

### Run Server
```bash
python manage.py runserver
```

### Docker (Postgres only)
```bash
docker-compose up -d    # Starts Postgres on port 5434
```

### Testing
```bash
# Run all tests
pytest -s

# Run a specific test file
pytest tests/products/test_products.py -s

# Run a specific test
pytest tests/products/test_products.py::TestTaxRates::test_create_percentage_tax_rate -s
```

**Test config:** `pytest.ini` sets `DJANGO_SETTINGS_MODULE = backend.settings`

---

## Environment Variables (`.env`)

| Variable           | Default / Example                         | Usage                |
| ------------------ | ----------------------------------------- | -------------------- |
| `DJANGO_ENV`       | `development`                             | Settings selection (development/production) |
| `SECRET_KEY`       | *(insecure default in dev)*               | Django secret key (required in production) |
| `DB_ENGINE`        | `django_tenants.postgresql_backend`       | Required for tenants |
| `DB_NAME`          | `omni_channel_db`                         | Postgres DB name     |
| `DB_USER`          | `omni_channel_admin`                      | Postgres user        |
| `DB_PASSWORD`      | *(set locally)*                           | Postgres password    |
| `DB_HOST`          | `localhost`                               | Postgres host        |
| `DB_PORT`          | `5432`                                    | Postgres port        |
| `DB_SSLMODE`       | *(empty)*                                 | Set `require` for cloud Postgres |
| `EMAIL_BACKEND`    | `django.core.mail.backends.console.EmailBackend` | Console in dev |
| `CELERY_BROKER_URL`| `redis://localhost:6379/0`                | Redis broker URL     |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0`           | Redis result backend |

---

## Important Notes

1. **Database must be PostgreSQL** — `django-tenants` requires PostgreSQL for schema-level isolation.
2. **Public tenant must exist** — After initial migration, create the public tenant via `manage.py shell`.
3. **Middleware order matters** — `TenantFromHeaderMiddleware` must be the **first** middleware.
4. **Settings split** — Settings live in `backend/settings/` package (base, development, production). Set `DJANGO_ENV` to switch.
5. **Migrations are gitignored** — `.gitignore` excludes `migrations/` directories. Run `makemigrations` locally.
6. **Re-export everything split modules expose.** When splitting `models.py` → `models/`, the `__init__.py` must re-export all classes referenced by migrations, serializers, views, or other apps.
7. **Lazy imports for circular dependencies.** Within split model packages, use lazy imports inside methods (`from .b import B`) rather than top-level imports.
8. **Schema file** — `schema.yml` is the pre-generated OpenAPI spec.
9. **Menu publishing is read-only on catalog.** Publishing builds payloads from Product/ProductLocation data without modifying it. Only MenuLocationChannel status/snapshot is written.
10. **Testing with tenants.** In tests, create products via the API (not direct ORM) to ensure they run in the correct tenant schema. Direct ORM queries after API calls run on public schema due to middleware reset.
11. **ProductChannelConfig writes through.** Saving a `ProductChannelConfig` automatically syncs price/availability to `ProductLocation.channels` JSONField. Deleting it removes the channel entry. Never update `ProductLocation.channels` and `ProductChannelConfig` independently — use one or the other.
12. **Product mutation signals.** `ProductLocation` save/delete fires Django signals that push menu changes to all active channel links for that location. Disable signals in tests if not testing integration sync (signals import `integrations.services`).
13. **Single active POS per location.** `ChannelLink.save()` enforces at most one active POS-type channel link per location. Different locations under the same merchant can use different POS systems.
14. **Per-product write protection.** `CatalogWriteProtectionMixin` on `ProductViewSet` blocks delete/update of core catalog fields based on `Product.managed_by` (not merchant-level). Platform-owned products (`managed_by="internal_pos"` or legacy `""`) are fully writable. External POS-managed products (`managed_by="clover"` etc.) have core fields read-only. Product creation is always allowed. Override layers (location pricing, availability, menu curation) remain writable.
15. **Product origin tracking.** `Product.managed_by` tracks catalog ownership: `"internal_pos"` = platform-owned (locally created or marketplace-seeded), external POS slug = POS-owned, `""` = legacy (treated as `"internal_pos"`). `INTERNAL_POS_SLUG` constant in `common/constants.py`. Ownership precedence: external POS > `"internal_pos"` > `""` (never downgrade). Stamped by `IntegrationSyncService.pull_and_persist()`. Read-only via API.
