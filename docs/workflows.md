# Workflows — Omnichannel POS & Order Management Hub

Complete reference for every workflow in the system, covering authentication, catalog management, channel integrations, menu publishing, order processing, and webhooks.

---

## Table of Contents

1. [Authentication & Tenant Setup](#1-authentication--tenant-setup)
2. [Merchant Management](#2-merchant-management)
3. [Location Management](#3-location-management)
4. [Product Catalog Management](#4-product-catalog-management)
5. [Tax Rate Management](#5-tax-rate-management)
6. [Category Management](#6-category-management)
7. [Channel & Integration Setup](#7-channel--integration-setup)
8. [Menu Management & Publishing](#8-menu-management--publishing)
9. [Order Management](#9-order-management)
10. [Webhook System](#10-webhook-system)
11. [Price Resolution](#11-price-resolution)
12. [Availability Resolution](#12-availability-resolution)
13. [Data Flow Diagrams](#13-data-flow-diagrams)

---

## 1. Authentication & Tenant Setup

### Register a New User

```
POST /api/v1/auth/users/
Body: { "email": "user@example.com", "password": "...", "first_name": "...", "last_name": "..." }
→ 201 Created
```

### Login (Obtain JWT Tokens)

```
POST /api/v1/auth/jwt/create/
Body: { "email": "user@example.com", "password": "..." }
→ 200 { "access": "<token>", "refresh": "<token>" }
```

### Refresh Token

```
POST /api/v1/auth/jwt/refresh/
Body: { "refresh": "<refresh_token>" }
→ 200 { "access": "<new_access_token>" }
```

### Required Headers for All Authenticated Requests

| Header          | Value                      | Required |
| --------------- | -------------------------- | -------- |
| `Authorization` | `Bearer <access_token>`    | Yes      |
| `X-Tenant-ID`   | `<merchant-uuid>`          | For tenant endpoints |
| `X-Location-ID`  | `<location-uuid>`         | Optional (context) |
| `X-Channel`      | `ubereats`, `doordash` …  | Optional (context) |

### Tenant Schema Switching

1. Request arrives with `X-Tenant-ID` header.
2. `TenantFromHeaderMiddleware` validates UUID, looks up `Merchant` in public schema.
3. Calls `connection.set_tenant(merchant)` → all ORM queries run against that tenant's schema.
4. After response, resets to public schema.
5. Tenant-only endpoints reject requests missing `X-Tenant-ID` with `400`.

---

## 2. Merchant Management

Merchants are tenants. Each merchant gets an isolated PostgreSQL schema.

### Create Merchant

```
POST /api/v1/merchants/
Headers: Authorization
Body: { "name": "My Restaurant" }
→ 201 { "id": "<uuid>", "name": "My Restaurant", "schema_name": "..." }
```

- Owner is auto-set to the authenticated user.
- Schema is auto-created (`auto_create_schema = True`).

### List Merchants

```
GET /api/v1/merchants/
→ 200 [ ... ] (filtered to user's own merchants)
```

### Update / Delete Merchant

```
PATCH /api/v1/merchants/{id}/   (requires IsMerchantOwner)
DELETE /api/v1/merchants/{id}/  (cascades schema deletion)
```

---

## 3. Location Management

Locations are physical stores or fulfillment points within a tenant.

```
POST /api/v1/locations/
Headers: Authorization, X-Tenant-ID
Body: { "name": "Downtown Store", "address": "...", "city": "...", "pincode": "..." }
→ 201 Created
```

Standard CRUD: `GET`, `POST`, `PUT`, `PATCH`, `DELETE` on `/api/v1/locations/` and `/api/v1/locations/{id}/`.

---

## 4. Product Catalog Management

### Product Types

| Value | Type           | Description                        |
| ----- | -------------- | ---------------------------------- |
| 1     | MAIN           | Sellable products (burgers, pizza) |
| 2     | MODIFIER_ITEM  | Options (lettuce, extra cheese)    |
| 3     | MODIFIER_GROUP | Container for modifier items       |
| 4     | BUNDLE_GROUP   | Container for bundle/combo items   |

### Product Nesting Rules

```
MAIN → [MODIFIER_GROUP, BUNDLE_GROUP]
MODIFIER_GROUP → [MODIFIER_ITEM, MAIN]
BUNDLE_GROUP → [MAIN]
MODIFIER_ITEM → [MODIFIER_GROUP]
```

### Create Product

```
POST /api/v1/products/
Headers: Authorization, X-Tenant-ID, (optional) X-Location-ID
Body: {
  "name": "Cheeseburger",
  "product_type": 1,
  "price": 999,
  "categories": ["<category-uuid>"],
  ...
}
→ 201 Created
```

- PLU is auto-generated if not provided (format: `{TYPE}-{SHORTNAME}-{RANDOM}`).
- If `X-Location-ID` is present, `ProductService.auto_assign_location()` creates a `ProductLocation` automatically.

### Bulk Sync (POS Import)

Atomically imports tax rates, categories, and products from an external POS system.

```
POST /api/v1/products/bulk_sync/
Headers: Authorization, X-Tenant-ID
Body: {
  "tax_rates": [{ "name": "VAT 9%", "percentage": 9000 }],
  "categories": [{ "pos_category_id": "CAT-1", "name": "Burgers" }],
  "products": [{ "plu": "MAIN-BURG-A1B2", "name": "Burger", ... }]
}
→ 200 { "success": true, "products_synced": 10, "categories_synced": 3, "tax_rates_synced": 2 }
```

Processing order: tax rates → categories → products (dependency order). Uses `update_or_create` for idempotent syncing.

### Export Menu

Exports products available at a location, formatted for channel consumption.

```
GET /api/v1/products/export_menu/
Headers: Authorization, X-Tenant-ID, X-Location-ID
Query: ?category_id=<uuid>&visible_only=true
→ 200 { "products": [...], "categories": [...], "metadata": {...} }
```

Filters: MAIN type only, available at location, optionally by category and visibility.

### Mark Products Unavailable (3-Scope)

```
POST /api/v1/products/mark_unavailable/
Headers: Authorization, X-Tenant-ID, (optional) X-Location-ID, (optional) X-Channel
Body: { "plus": ["PLU1", "PLU2"], "tags": [1, 2] }
```

| Headers Present             | Scope    | Effect                                      |
| --------------------------- | -------- | ------------------------------------------- |
| None                        | Global   | `Product.visible = False`                    |
| `X-Location-ID`             | Location | `ProductLocation.is_available = False`       |
| `X-Location-ID` + `X-Channel` | Channel  | `channels[slug].is_available = False`     |

### Update Location Pricing

```
PATCH /api/v1/products/{plu}/update_location_pricing/
Headers: Authorization, X-Tenant-ID, X-Location-ID
Body: {
  "price_override": 1199,
  "is_available": true,
  "channels": { "ubereats": { "price": 1299, "is_available": true } },
  "stock_quantity": 50,
  "low_stock_threshold": 5
}
→ 200 { ... updated fields ... }
```

### Bulk Delete

```
POST /api/v1/products/bulk_delete/
Body: { "plus": ["PLU1", "PLU2"] }
→ 200 { "success": true, "deleted": 2, "not_found": [] }
```

---

## 5. Tax Rate Management

### Tax Rate Types

- **Percentage-based**: `percentage` field (stored as value × 1000, e.g., 9% = 9000)
- **Flat-fee**: `flat_fee` field (in cents)
- Mutually exclusive — a tax rate has one or the other.

### Default Tax Rate

Setting `is_default = True` auto-unsets any existing default (atomic swap).

### 3-Tier Tax Resolution

```
Location override (ProductLocation tax fields)
  → Product default (Product tax fields)
    → Merchant default (is_default=True TaxRate)
```

Tax is resolved per service type: `delivery_tax_rate`, `takeaway_tax_rate`, `eat_in_tax_rate`.

### CRUD

```
GET/POST /api/v1/tax-rates/
GET/PUT/PATCH/DELETE /api/v1/tax-rates/{id}/
```

---

## 6. Category Management

Categories group products for organization and display.

```
GET/POST /api/v1/categories/
GET/PUT/PATCH/DELETE /api/v1/categories/{pos_category_id}/
```

- Lookup field: `pos_category_id` (not UUID).
- Supports `name_translations` (JSON) for multi-language.
- `sort_order` for display ordering.

---

## 7. Channel & Integration Setup

### Channels (Global, Read-Only)

Channels are platform definitions shared across all tenants.

```
GET /api/v1/channels/
→ 200 [
  { "slug": "ubereats", "display_name": "Uber Eats", "channel_type": "marketplace", "direction": "bidirectional", ... },
  { "slug": "internal_pos", "display_name": "Internal POS", "channel_type": "pos", ... }
]
```

Each channel specifies:
- `adapter_class`: Dotted path to the Python adapter (e.g., `integrations.adapters.internal_pos.InternalPOSAdapter`)
- `config_schema`: JSON Schema defining required credentials

### Channel Links (Per-Tenant, Per-Location)

A ChannelLink connects a tenant's location to an external channel.

```
POST /api/v1/channel-links/
Headers: Authorization, X-Tenant-ID
Body: {
  "channel": "<channel-uuid>",
  "location": "<location-uuid>",
  "credentials": { "api_key": "...", "store_id": "..." },
  "external_store_id": "EXT-123"
}
→ 201 Created
```

Unique constraint: one link per channel-location pair.

### Validate Credentials

```
POST /api/v1/channel-links/{id}/validate/
→ 200 { "valid": true }
```

Calls `adapter.validate_credentials()` to test API keys against the external platform.

### Sync Menu to Channel

```
POST /api/v1/channel-links/{id}/sync_menu/
→ 200 { "success": true, "message": "...", "updated_count": 15, "created_count": 3 }
```

1. Builds `CanonicalMenu` from product queryset.
2. Calls `adapter.push_menu(canonical_menu)`.
3. Updates `sync_status` and `last_sync_at` on the ChannelLink.

### Product Channel Config (Per-Product Overrides)

```
POST /api/v1/product-channel-configs/
Body: {
  "product_location": "<product-location-uuid>",
  "channel": "<channel-uuid>",
  "price": 1299,
  "is_available": true,
  "external_product_id": "EXT-PROD-456"
}
```

### Adapter Pattern

All channel integrations implement `AbstractChannelAdapter`:

| Method                        | Purpose                                |
| ----------------------------- | -------------------------------------- |
| `push_menu(canonical_menu)`   | Send menu to external platform         |
| `pull_menu()`                 | Fetch menu from external platform      |
| `normalize_inbound_order()`   | Parse webhook payload → CanonicalOrder |
| `update_order_status()`       | Notify platform of status change       |
| `update_availability()`       | Toggle item availability               |
| `validate_credentials()`      | Test API credentials                   |
| `verify_webhook_signature()`  | Verify HMAC on inbound webhooks        |
| `handle_webhook()`            | Process webhook event                  |

**Internal POS** is implemented as an adapter where `push_menu()` is a no-op (database is source of truth) and `pull_menu()` reads directly from the catalog.

---

## 8. Menu Management & Publishing

### Concept

A **Menu** is a merchant-level entity (not location-level) that curates products into customer-facing categories. A single menu can be assigned to multiple locations, each publishing to different channels.

### Create a Menu

```
POST /api/v1/menus/
Headers: Authorization, X-Tenant-ID
Body: { "name": "Lunch Menu", "description": "...", "is_active": true }
→ 201 Created
```

### Add Categories to a Menu

```
POST /api/v1/menus/{menu_id}/categories/
Body: { "name": "Starters", "sort_order": 1 }
→ 201 Created
```

### Add Items to a Category

```
POST /api/v1/menus/{menu_id}/items/
Body: {
  "menu_category": "<category-uuid>",
  "product": "<product-uuid>",
  "sort_order": 1,
  "price_override": 1099,  // optional menu-level price
  "is_visible": true
}
→ 201 Created
```

- Validates that `menu_category` belongs to the menu.
- Enforces uniqueness: a product can only appear once per menu (across all categories).

### Set Availability Windows

```
POST /api/v1/menus/{menu_id}/availabilities/
Body: {
  "day_of_week": 1,
  "start_time": "11:00:00",
  "end_time": "14:00:00",
  "start_date": "2026-03-01",  // optional seasonal
  "end_date": "2026-09-30"
}
→ 201 Created
```

### Assign Menu to Locations

```
POST /api/v1/menus/{menu_id}/locations/
Body: { "location": "<location-uuid>" }
→ 201 Created
```

### Assign Channels to a Menu-Location

```
POST /api/v1/menus/{menu_id}/locations/{loc_id}/channels/
Body: { "channel_link": "<channel-link-uuid>" }
→ 201 Created
```

### Publish Menu

```
POST /api/v1/menus/{menu_id}/publish/
→ 200 {
  "published": 3,
  "results": [
    {
      "location": "Downtown Store",
      "channel": "ubereats",
      "status": "published",
      "error": null,
      "snapshot": { ... full payload ... }
    },
    ...
  ]
}
```

**Publishing workflow:**

1. Finds all active `MenuLocationChannel` records for the menu.
2. For each, calls `MenuPublisherService.build_payload()`:
   - Iterates categories and items.
   - Skips invisible, inactive, or unavailable products.
   - Resolves prices via the 5-level fallback chain.
   - Includes availability windows.
3. Gets adapter via `AdapterRegistry.get_adapter(channel_link)`.
4. Calls `adapter.push_menu(payload)`.
5. Stores status (`published` / `failed`), snapshot, timestamp, and any error.

**Publishing is READ-only on catalog data.** It does not modify products, locations, or pricing. It only writes to `MenuLocationChannel` (status, snapshot) and the external platform.

### Check Publish Status

```
GET /api/v1/menus/{menu_id}/publish-status/
→ 200 [ { "status": "published", "published_at": "...", ... }, ... ]
```

### Duplicate Menu

```
POST /api/v1/menus/{menu_id}/duplicate/
Body: { "name": "Lunch Menu (Copy)" }  // optional
→ 201 { ... new menu ... }
```

Copies categories, items, and availabilities. Does NOT copy location assignments. New menu starts inactive.

---

## 9. Order Management

### Order Lifecycle (State Machine)

```
RECEIVED → ACCEPTED → PREPARING → READY → PICKED_UP → DELIVERED → COMPLETED
                                        ↘ CANCELLED
           REJECTED ←────────────────────┘
           FAILED
```

### Order Types

| Type       | Description                |
| ---------- | -------------------------- |
| DELIVERY   | Delivered to customer      |
| TAKEAWAY   | Customer picks up          |
| EAT_IN     | Dine-in                    |
| PICKUP     | Curbside or counter pickup |

### Inbound Order (from External Channel)

Orders arrive via webhooks. See [Webhook System](#10-webhook-system).

1. External platform sends `POST /api/v1/webhooks/inbound/{channel_link_id}/`.
2. System verifies HMAC signature.
3. Adapter normalizes payload → `CanonicalOrder`.
4. `OrderService.create_order_from_canonical()`:
   - Creates `Order` with financials, customer info, timing.
   - Creates `OrderItem` records (with modifiers).
   - Creates initial `OrderStatusLog` (status: RECEIVED).
5. Returns acknowledgment to external platform.

### Update Order Status

```
PATCH /api/v1/orders/{id}/status/
Headers: Authorization, X-Tenant-ID
Body: { "status": "accepted" }
→ 200 { ... updated order ... }
```

1. Validates transition against state machine.
2. Sets timestamp field (`accepted_at`, `ready_at`, etc.).
3. Creates `OrderStatusLog`.
4. If order has a `channel_link`, notifies external platform via `adapter.update_order_status()`.

### Order Financials

All monetary values in **cents**:

| Field          | Description              |
| -------------- | ------------------------ |
| subtotal       | Sum of item prices       |
| tax_total      | Total tax                |
| delivery_fee   | Delivery charge          |
| service_fee    | Platform service fee     |
| tip            | Customer tip             |
| discount_total | Applied discounts        |
| total          | Final amount             |

---

## 10. Webhook System

### Inbound Webhooks (from External Platforms)

```
POST /api/v1/webhooks/inbound/{channel_link_id}/
(No JWT required — uses HMAC signature verification)
```

**Flow:**
1. Request arrives without JWT (external platform).
2. System resolves tenant by searching schemas for the `channel_link_id`.
3. Gets adapter via `AdapterRegistry`.
4. Calls `adapter.verify_webhook_signature(payload, headers)` — HMAC validation.
5. Calls `adapter.handle_webhook(event_type, payload, headers)`.
6. For `new_order` events: normalizes and creates order.
7. Logs everything in `WebhookLog`.
8. Returns `WebhookResult` → `200 OK`.

### Outbound Webhooks (to Merchant Endpoints)

Merchants register endpoints to receive notifications about events in their tenant.

```
POST /api/v1/webhooks/endpoints/
Headers: Authorization, X-Tenant-ID
Body: {
  "url": "https://merchant.com/hooks",
  "secret": "hmac-secret-key",
  "events": ["order.created", "order.status_changed"],
  "is_active": true
}
```

When events occur, the system:
1. Finds matching active endpoints by event type.
2. Signs the payload with the endpoint's `secret` (HMAC).
3. Sends POST to the endpoint URL.
4. Logs attempt in `WebhookLog` (success/failure, response status, retry info).

### Webhook Logs

```
GET /api/v1/webhooks/logs/
→ 200 [
  {
    "direction": "inbound",
    "channel_slug": "ubereats",
    "event_type": "new_order",
    "success": true,
    "attempts": 1,
    ...
  }
]
```

Read-only. Used for debugging and auditing.

---

## 11. Price Resolution

### 5-Level Fallback Chain (Menu Publishing)

When publishing a menu item to a channel, the price is resolved in order:

```
1. Menu-level override     → MenuItem.price_override
2. Channel-specific price  → ProductLocation.channels[slug].price
3. Location price          → ProductLocation.price_override
4. Product base price      → Product.price
5. Default fallback        → Product.price (same as 4)
```

First non-null value wins.

### Product Price Resolution (Catalog)

```
1. Channel price → ProductLocation.channels[slug].price
2. Location price → ProductLocation.price_override
3. Product price → Product.price
```

### Context-Dependent Pricing (Overloads)

Products support `overloads` — context-dependent pricing within hierarchies:

```json
{
  "overloads": [
    { "scopes": ["PARENT-PLU"], "price": 0, "bundle_price": 100 }
  ]
}
```

Example: Extra Cheese is $1.50 normally, but $0 when added to a Combo Meal.

---

## 12. Availability Resolution

### 3-Scope Availability

| Scope    | Field                                        | Effect                                |
| -------- | -------------------------------------------- | ------------------------------------- |
| Global   | `Product.visible`                            | Hidden everywhere                     |
| Location | `ProductLocation.is_available`               | Unavailable at specific location      |
| Channel  | `ProductLocation.channels[slug].is_available` | Unavailable on specific channel only |

Checked in order during menu publishing. If any level is `False`, the product is skipped.

### Menu Availability Windows

`MenuAvailability` defines when a menu is active:

- `day_of_week`: 0 (Monday) – 6 (Sunday)
- `start_time` / `end_time`: Daily time window
- `start_date` / `end_date`: Optional seasonal bounds

Multiple windows can overlap (e.g., different hours on weekdays vs weekends).

---

## 13. Data Flow Diagrams

### End-to-End: Menu Creation to Channel Publishing

```
1. Create Menu
   POST /menus/

2. Add Categories
   POST /menus/{id}/categories/

3. Add Items (products from catalog)
   POST /menus/{id}/items/

4. Set Availability Windows
   POST /menus/{id}/availabilities/

5. Assign to Locations
   POST /menus/{id}/locations/

6. Assign Channels per Location
   POST /menus/{id}/locations/{loc}/channels/

7. Publish
   POST /menus/{id}/publish/
   → Builds payload (reads catalog)
   → Resolves prices (5-level chain)
   → Filters by availability
   → Pushes via adapter
   → Stores snapshot
```

### End-to-End: Inbound Order Processing

```
1. External Platform → POST /webhooks/inbound/{channel_link_id}/
2. Resolve Tenant (search schemas for ChannelLink)
3. Verify HMAC Signature (adapter.verify_webhook_signature)
4. Parse Payload → CanonicalOrder (adapter.normalize_inbound_order)
5. Create Order + OrderItems + OrderModifiers
6. Set Status: RECEIVED
7. Log in WebhookLog
8. Return 200 OK

Later:
9.  Merchant accepts → PATCH /orders/{id}/status/ { "status": "accepted" }
10. Adapter notifies external platform
11. Status progresses: PREPARING → READY → PICKED_UP → DELIVERED → COMPLETED
```

### End-to-End: Product Catalog Sync from POS

```
1. POS System sends bulk data
   POST /products/bulk_sync/
   Body: { tax_rates, categories, products }

2. Process in dependency order:
   Tax Rates → update_or_create by name
   Categories → update_or_create by pos_category_id
   Products → update_or_create by PLU

3. All within @transaction.atomic (all or nothing)

4. Products auto-generate PLUs if not provided

5. Assign to locations:
   PATCH /products/{plu}/update_location_pricing/
   Headers: X-Location-ID
```

### Internal POS vs Channel Publishing

```
Internal POS:
  POS Terminal → reads Product/ProductLocation directly from DB
  No menu publishing needed
  InternalPOSAdapter.push_menu() = no-op
  InternalPOSAdapter.pull_menu() = reads from catalog

Channel Publishing:
  Menu → MenuLocation → MenuLocationChannel
  Publishing = READ catalog → BUILD payload → PUSH to external platform
  Snapshot stored on MenuLocationChannel
  Does NOT modify catalog data
```

### Canonical Data Layer

```
CanonicalMenu:
  Normalizes menu data across platforms
  Built from product queryset
  Contains: location, channel, categories, products (with prices, modifiers)

CanonicalOrder:
  Normalizes order data from external webhooks
  Contains: external_id, customer, items, financials, timing
  Methods: from_dict(), to_order_kwargs(), to_dict()

SyncResult:
  Returned by push_menu(), update_availability()
  Contains: success, message, counts, errors, external_ids

WebhookResult:
  Returned by handle_webhook()
  Contains: success, action, message, order_id
```
