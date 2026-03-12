# Multi-Location, Multi-Channel Menu System

## Overview

A **Menu** is a merchant-level entity that defines **what to sell** (items + structure + schedule). It gets **assigned to locations** and **published to channels at those locations**. Pricing, availability, and stock are not duplicated — they resolve from the existing catalog layer at publish time.

### Core Idea

```
Product Catalog (what exists)
       |  select into
     Menu (what to show, when, where)
       |  publish to
   Channel Link (the destination)
```

---

## Model Structure

```
Menu (merchant-level)
|
+-- MenuCategory (1:M)
|   +-- MenuItem (1:M)
|       +-- product -> Product (FK to catalog)
|
+-- MenuAvailability (1:M)
|
+-- MenuLocation (1:M -- which locations)
    +-- MenuLocationChannel (1:M -- which channels at that location)
```

### Menu

| Field       | Type     | Description                                  |
|-------------|----------|----------------------------------------------|
| id          | UUID     | Primary key                                  |
| name        | str      | "Breakfast Menu", "Late Night Menu"          |
| description | str      | Optional                                     |
| image_url   | URL      | Optional banner/cover image                  |
| is_active   | bool     | Master toggle                                |
| sort_order  | int      | Display ordering when listing merchant menus |
| created_at  | datetime | Auto                                         |
| updated_at  | datetime | Auto                                         |

### MenuCategory

| Field       | Type           | Description                              |
|-------------|----------------|------------------------------------------|
| id          | UUID           | Primary key                              |
| menu        | FK -> Menu     | Parent menu                              |
| name        | str            | "Morning Favourites", "Chef's Picks"     |
| description | str            | Optional                                 |
| image_url   | URL            | Optional                                 |
| sort_order  | int            | Display order within the menu            |
| created_at  | datetime       | Auto                                     |
| updated_at  | datetime       | Auto                                     |

**Unique constraint:** `(menu, name)`

> **Why not reuse products.Category?** Catalog categories ("Burgers") are for internal organization and POS sync. Menu categories ("Signature Burgers", "Chef's Picks") are customer-facing and can differ per menu — different names, different sort orders, different groupings.

### MenuItem

| Field          | Type                 | Description                                          |
|----------------|----------------------|------------------------------------------------------|
| id             | UUID                 | Primary key                                          |
| menu_category  | FK -> MenuCategory   | Parent category within the menu                      |
| product        | FK -> Product        | Points back to the product catalog                   |
| sort_order     | int                  | Display order within the category                    |
| price_override | int (nullable)       | Menu-level price override in cents (null = use catalog/location price) |
| is_visible     | bool (default True)  | Hide from this menu without touching catalog         |
| created_at     | datetime             | Auto                                                 |
| updated_at     | datetime             | Auto                                                 |

**Unique constraint:** `(menu_category__menu, product)` — a product appears once per menu.

> MenuItem does NOT duplicate product data — name, description, modifiers, images all come from the catalog Product. Only overrides are stored here.

### MenuAvailability

| Field       | Type             | Description                          |
|-------------|------------------|--------------------------------------|
| id          | UUID             | Primary key                          |
| menu        | FK -> Menu       | Parent menu                          |
| day_of_week | int (0-6)        | 0=Monday ... 6=Sunday               |
| start_time  | TimeField        | e.g. 07:00                          |
| end_time    | TimeField        | e.g. 12:00                          |
| start_date  | DateField (null) | Optional: seasonal start (e.g. Dec 1)  |
| end_date    | DateField (null) | Optional: seasonal end (e.g. Feb 28)   |
| created_at  | datetime         | Auto                                 |

**Unique constraint:** `(menu, day_of_week, start_time)`

A menu with **no availability rows = always available**.

### MenuLocation

| Field      | Type            | Description                              |
|------------|-----------------|------------------------------------------|
| id         | UUID            | Primary key                              |
| menu       | FK -> Menu      | Parent menu                              |
| location   | FK -> Location  | Which location uses this menu            |
| is_active  | bool            | Toggle this menu at this specific location |
| created_at | datetime        | Auto                                     |
| updated_at | datetime        | Auto                                     |

**Unique constraint:** `(menu, location)`

### MenuLocationChannel

| Field         | Type                  | Description                              |
|---------------|-----------------------|------------------------------------------|
| id            | UUID                  | Primary key                              |
| menu_location | FK -> MenuLocation    | Parent menu-location                     |
| channel_link  | FK -> ChannelLink     | The target (location + channel pair)     |
| status        | enum                  | draft / published / failed               |
| published_at  | datetime (nullable)   | When last published                      |
| published_by  | FK -> User (nullable) | Who published                            |
| snapshot      | JSONField             | Frozen copy of what was pushed           |
| error_message | str                   | Publish error details                    |
| created_at    | datetime              | Auto                                     |
| updated_at    | datetime              | Auto                                     |

**Unique constraint:** `(menu_location, channel_link)`

---

## Relationship Diagram

```
Merchant (tenant)
|
|  +-------------- CATALOG LAYER (existing, unchanged) ---------------+
|  |                                                                   |
|  |  Product <--M2M--> Category                                      |
|  |     |                                                             |
|  |     +-- ProductRelation (modifiers, bundles)                     |
|  |     |                                                             |
|  |     +-- ProductLocation (product + location junction)            |
|  |            |         +-- price_override                          |
|  |            |         +-- channels (JSONField) ← single source    |
|  |            |         +-- is_available                            |
|  |            |         +-- tax overrides                           |
|  |            |         +-- signals → push_to_active_channels()     |
|  |            |                                                      |
|  |            +-- ProductChannelConfig (admin API, writes through)  |
|  |                                                                   |
|  |  Location                                                         |
|  |     +-- ChannelLink (location + channel + credentials)           |
|  |                                                                   |
|  +-------------------------------------------------------------------+
|
|  +-------------- MENU LAYER (new) ----------------------------------+
|  |                                                                   |
|  |  Menu                                                             |
|  |     +-- MenuCategory                                             |
|  |     |      +-- MenuItem -> Product (FK to catalog)               |
|  |     |                                                             |
|  |     +-- MenuAvailability (daypart windows)                       |
|  |     |                                                             |
|  |     +-- MenuLocation (which locations)                           |
|  |            +-- MenuLocationChannel (which channels)              |
|  |                   +-- channel_link -> ChannelLink                |
|  |                                                                   |
|  +-------------------------------------------------------------------+
```

---

## How Existing Models Interact With Menus

| Existing Model       | Role in Menu Context                                                                                                                              |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| Product              | MenuItem points to it. All product data (name, description, modifiers, images, base price) comes from here. The menu never duplicates this.       |
| Category (products)  | Catalog-level grouping. Stays for internal organization, POS sync, and filtering. Menu uses its own MenuCategory for customer-facing grouping.     |
| ProductLocation      | Resolved at publish time. When publishing a menu to a location+channel, the system checks: does this product have a ProductLocation? Is it available? What's the channel price? If not stocked, it's skipped. |
| ProductChannelConfig | Provides `external_product_id` for each product on each channel. Used during publish to map internal PLUs to platform item IDs.                   |
| ChannelLink          | MenuLocationChannel points to this. It's the destination — "Location A's connection to UberEats, with credentials and external store ID."         |
| ProductRelation      | Modifier groups and bundle groups travel with the product. If Cheeseburger is in a menu, its modifier tree comes along automatically.              |
| TaxRate              | Resolved from the catalog layer (product -> location override -> merchant default). The menu doesn't deal with tax.                                |

---

## Pricing Resolution (Full Chain)

When building the published menu payload for a specific MenuItem at a specific Location on a specific Channel:

```
Step 1: MenuItem.price_override                -> Menu-specific price
        | null? continue
        v
Step 2: ProductLocation.channels[ch]["price"]  -> Channel price at location (single source of truth)
        | not set? continue                       (ProductChannelConfig writes through to this on save)
        v
Step 3: ProductLocation.price_override         -> Location base price
        | null? continue
        v
Step 4: Product.price                          -> Catalog base price
```

> **Note:** `ProductChannelConfig` is the admin/API-facing model for managing channel-specific pricing. On save, it writes through to `ProductLocation.channels` JSONField via `_sync_to_product_location()`. On delete, it removes the channel entry. This means `ProductLocation.channels` is always the single source of truth for price resolution — there is no separate lookup against `ProductChannelConfig` at publish time.

### When to Use Each Level

| Level                          | Use Case                                                                                      |
|--------------------------------|-----------------------------------------------------------------------------------------------|
| MenuItem.price_override        | "Pancakes cost $5.99 on our Breakfast Menu, but $7.99 on the All-Day Menu"                    |
| ProductChannelConfig / ProductLocation.channels | "This product always costs $11.99 on UberEats at Location A" (same data — ProductChannelConfig writes through to the JSONField) |
| ProductLocation.price_override | "Everything at the airport location costs $2 more"                                            |
| Product.price                  | "The default catalog price"                                                                   |

---

## Use Cases

### 1. Basic: One Location, One Menu, Two Channels

> A small cafe with one location, a single menu, connected to UberEats and DoorDash.

```
Menu: "Our Menu"
+-- MenuCategory: "Coffee"
|   +-- Latte
|   +-- Cappuccino
|   +-- Espresso
+-- MenuCategory: "Pastries"
|   +-- Croissant
|   +-- Muffin
+-- MenuAvailability: (none -- always available)
+-- MenuLocation: Location A
    +-- MenuLocationChannel -> ChannelLink(Location A, UberEats)  [published]
    +-- MenuLocationChannel -> ChannelLink(Location A, DoorDash)  [published]
```

Same menu structure pushed to both channels, but each gets its own resolved prices from the catalog layer.

---

### 2. Daypart Menus at One Location

> A restaurant with Breakfast, Lunch, and Dinner menus at a single location.

```
Menu: "Breakfast"
+-- Items: Pancakes, Eggs Benedict, Coffee, OJ
+-- MenuAvailability:
|   +-- Mon-Fri: 07:00 - 11:30
|   +-- Sat-Sun: 08:00 - 13:00
+-- MenuLocation: Downtown
    +-- -> UberEats [published]
    +-- -> Internal POS [published]

Menu: "Lunch"
+-- Items: Burger, Salad, Soup, Fries
+-- MenuAvailability:
|   +-- Mon-Fri: 11:30 - 17:00
|   +-- Sat-Sun: 13:00 - 17:00
+-- MenuLocation: Downtown
    +-- -> UberEats [published]
    +-- -> DoorDash [published]
    +-- -> Internal POS [published]

Menu: "Dinner"
+-- Items: Steak, Pasta, Wine, Beer
+-- MenuAvailability:
|   +-- Mon-Sun: 17:00 - 23:00
+-- MenuLocation: Downtown
    +-- -> Internal POS [published]
        (no delivery channels -- dinner is dine-in only)
```

- Pancakes only appear during breakfast hours.
- Wine/Beer are on Dinner menu only, never pushed to delivery channels.
- Lunch is on 3 channels, Dinner is POS-only.
- Coffee could be in both Breakfast and Lunch menus (as separate MenuItems with different sort orders or categories).

---

### 3. Same Menu Across Multiple Locations

> A burger chain with 5 locations sharing the same "Main Menu".

```
Menu: "Main Menu"
+-- MenuCategory: "Burgers"
|   +-- Cheeseburger
|   +-- Veggie Burger
|   +-- Double Smash
+-- MenuCategory: "Sides"
|   +-- Fries
|   +-- Onion Rings
+-- MenuAvailability: (none -- always available)
|
+-- MenuLocation: Location A (Downtown)
|   +-- -> UberEats [published]
|   +-- -> DoorDash [published]
|
+-- MenuLocation: Location B (Mall)
|   +-- -> UberEats [published]
|   +-- -> Internal POS [published]
|
+-- MenuLocation: Location C (Airport)
    +-- -> UberEats [published]
```

**Published output differs per location:**

| Product       | Location A (Downtown) | Location B (Mall) | Location C (Airport)                           |
|---------------|-----------------------|--------------------|-------------------------------------------------|
| Cheeseburger  | $8.99 (base)          | $8.99 (base)       | $12.99 (airport ProductLocation.price_override) |
| Veggie Burger | $9.99                 | $9.99              | **Skipped** (no ProductLocation -- not stocked) |
| Double Smash  | $13.99                | $13.99             | $16.99                                          |

The menu structure is identical, but pricing and stocking resolve from the catalog layer.

---

### 4. Channel-Specific Menus

> A restaurant wants a smaller, curated menu on delivery apps but the full menu in-house.

```
Menu: "Full Menu"
+-- Categories: Starters, Mains, Desserts, Drinks, Kids, Specials (80 items)
+-- MenuLocation: Location A
    +-- -> Internal POS [published]

Menu: "Delivery Menu"
+-- Categories: Popular Mains, Quick Bites, Drinks (30 items -- subset)
+-- MenuLocation: Location A
    +-- -> UberEats [published]
    +-- -> DoorDash [published]

Menu: "Late Night Delivery"
+-- Categories: Snacks, Drinks (10 items -- minimal)
+-- MenuAvailability:
|   +-- Mon-Sun: 22:00 - 02:00
+-- MenuLocation: Location A
    +-- -> UberEats [published]
```

Same location, 3 different menus for different contexts. The product catalog is the same — each menu curates a different subset.

---

### 5. Multi-Location Chain With Regional Differences

> A pizza chain with 3 regions. Menu is mostly the same but with regional items.

```
Menu: "Standard Menu"
+-- Margherita, Pepperoni, BBQ Chicken, Garlic Bread, Coke
+-- MenuLocation: NYC Store     -> UberEats, DoorDash
+-- MenuLocation: LA Store      -> UberEats, DoorDash
+-- MenuLocation: Chicago Store -> UberEats, GrubHub

Menu: "NYC Specials"
+-- NY-Style Fold Slice, Cannoli
+-- MenuLocation: NYC Store     -> UberEats, DoorDash

Menu: "Chicago Specials"
+-- Deep Dish Pizza, Italian Beef
+-- MenuLocation: Chicago Store -> UberEats, GrubHub
```

Margherita pizza exists in the catalog **once**. It's in the "Standard Menu" assigned to all 3 locations. Each location resolves its own price via ProductLocation. Regional items are in separate menus assigned only to relevant locations.

---

### 6. Seasonal / Promotional Menu

> A holiday promotion that runs for 2 weeks across select locations.

```
Menu: "Valentine's Special"
+-- MenuItem: Heart-Shaped Pizza (price_override: $14.99 -- promo price)
+-- MenuItem: Chocolate Lava Cake (price_override: $6.99)
+-- MenuItem: Rose Lemonade
+-- MenuAvailability:
|   +-- Mon-Sun: 11:00 - 22:00
|       start_date: 2026-02-07
|       end_date: 2026-02-14
+-- MenuLocation: Downtown  -> UberEats, DoorDash, Internal POS
+-- MenuLocation: Mall      -> UberEats, Internal POS
    (Airport location excluded -- not participating)
```

After Feb 14, the menu is no longer active (end_date passed). No manual cleanup needed. The products remain in the catalog for next year.

---

## Internal POS vs Channel Publishing

### Case 1: Internal POS

The POS does **not need menus**. It reads directly from the catalog layer.

```
POS at Location A
  -> Query: ProductLocation where location=A, is_available=True
  -> Gets: All stocked products with location pricing
  -> Modifiers: Resolved from ProductRelation
  -> Tax: Resolved from ProductLocation tax overrides
```

The POS shows everything the location has. The existing `Product + ProductLocation + ProductRelation` handles this completely. No menu publish needed unless the merchant explicitly wants to restrict what POS shows.

When products are platform-owned (`managed_by="internal_pos"`), the merchant has full CRUD over them via the Products API.

### Case 1b: External POS (Clover, Square, Toast)

When an external POS is active at a location:

```
External POS (Clover)
  -> POST /channel-links/{id}/pull_menu/
  -> Products imported with managed_by = "clover"
  -> Core catalog fields become READ-ONLY via API
  -> Override layers remain writable:
     - Location pricing (update_location_pricing)
     - Channel pricing (product-channel-configs)
     - Availability (mark_unavailable)
     - Menu curation (all /menus/ endpoints)
     - Menu publishing (publish)
```

Products flow **one way**: POS -> Platform -> Delivery Channels. Changes to product name, price, or description must be made in the external POS and re-synced via `pull_menu`. Menu curation (which items to show, in what structure, at what menu-level price) is always controlled by the platform regardless of POS source.

### Case 1c: Marketplace Seeding (UberEats, DoorDash)

When pulling from a marketplace channel, products are seeded as platform-owned:

```
Marketplace (UberEats)
  -> POST /channel-links/{id}/pull_menu/
  -> Products seeded with managed_by = "internal_pos"
  -> Platform becomes source of truth
  -> All fields remain FULLY WRITABLE via API
  -> Existing external POS-managed products are NOT downgraded
     (ownership precedence: external POS > internal_pos > "")
```

This allows merchants to bootstrap their catalog from a marketplace and then manage it directly through the platform.

### Case 2: Publishing to Multiple Channels

**Publishing a menu does NOT write anything back to the catalog layer.** It is a READ operation on your data and a WRITE operation to the external platform.

```
Publish "Breakfast Menu" to Location A -> UberEats

  READS from DB (no modifications):
  +-- MenuItem list, Product data, ProductLocation, ProductChannelConfig, MenuAvailability

  BUILDS: CanonicalMenu payload

  WRITES to external: adapter.push_menu() -> UberEats API

  WRITES to DB (publish state only):
  +-- MenuLocationChannel.status = "published"
  +-- MenuLocationChannel.published_at = now()
  +-- MenuLocationChannel.snapshot = {the payload sent}
```

Same menu to a second channel resolves different prices (channel-specific) and builds a separate payload. Same menu to a second location resolves different stocking and pricing. Each publish is independent.

```
Merchant hits "Publish" on Breakfast Menu

+-- MenuLocation: Location A
|   +-- UberEats  -> payload A1, pushes to UberEats store A
|   +-- DoorDash  -> payload A2, pushes to DoorDash store A
+-- MenuLocation: Location B
    +-- UberEats  -> payload B1, pushes to UberEats store B

3 independent publishes. 3 payloads. 3 snapshots. 0 catalog modifications.
```

### What Each Layer Does During Publish

| Layer                          | Read / Write      | What                                           |
|--------------------------------|-------------------|-------------------------------------------------|
| Menu, MenuCategory, MenuItem   | Read              | Structure -- what items, what order             |
| MenuAvailability               | Read              | Schedule -- when this menu is active            |
| Product                        | Read              | Item data -- name, description, image, modifiers|
| ProductLocation                | Read              | Stocking + pricing for this location (incl. channel-specific via `.channels` JSONField) |
| ProductChannelConfig           | Read              | External product ID for this channel (price/availability already synced to ProductLocation.channels) |
| ChannelLink                    | Read              | Credentials + external store ID                 |
| Adapter                        | External write    | Pushes payload to platform API                  |
| MenuLocationChannel            | Write             | Status, snapshot, published_at                  |

ProductLocation is only modified through catalog operations (POS sync, mark unavailable, update pricing, stock update) -- completely separate from menu publishing.

---

## Availability & Unavailability

### Three Existing Scopes (Catalog Layer — Unchanged)

| Scope                  | How                                                        | Effect                                            |
|------------------------|------------------------------------------------------------|---------------------------------------------------|
| Global (catalog)       | `Product.visible = False`                                  | Excluded from ALL menus at ALL locations           |
| Location               | `ProductLocation.is_available = False`                     | Excluded from menus published at THAT location     |
| Channel                | `ProductLocation.channels[ch]["is_available"] = False`     | Excluded from menus published to THAT channel at that location |

### How It Cascades Through Menus

**Example: Lettuce supplier issue**

```
Set Product.visible = False for "Lettuce" (catalog-level)
  -> ANY menu containing Lettuce -> Lettuce excluded at publish time
  -> No need to edit each menu individually
  -> When resolved: set visible = True, re-publish

Set ProductLocation.is_available = False for "Lettuce" at Location A only
  -> Menus published at Location A -> Lettuce excluded
  -> Menus published at Location B -> Lettuce still included
  -> Menu structure itself is unchanged

Set ProductLocation.channels["ubereats"]["is_available"] = False at Location A
  -> Location A + UberEats -> Lettuce excluded
  -> Location A + DoorDash -> Lettuce still included
  -> Location A + Internal POS -> Lettuce still included
```

The menu layer doesn't interfere with availability — it's resolved at publish time.

---

## Publishing Workflow

```
Step 1: Merchant builds menu
        -> Creates Menu, adds MenuCategories, adds MenuItems

Step 2: Merchant assigns locations
        -> Creates MenuLocation rows

Step 3: Merchant selects channels per location
        -> Creates MenuLocationChannel rows (status: draft)

Step 4: Merchant hits "Publish"
        -> For each MenuLocationChannel:
           a. Resolve all items:
              - Check ProductLocation exists for this location
              - Check is_available (location-level)
              - Check is_available_on_channel (channel-level)
              - Check Product.visible (catalog-level)
           b. Resolve pricing per item:
              - MenuItem.price_override -> ProductChannelConfig.price
                -> ProductLocation.channels[ch] -> ProductLocation.price_override
                -> Product.price
           c. Resolve modifiers:
              - From ProductRelation, with their own pricing resolution
           d. Build CanonicalMenu payload (existing dataclass)
           e. Call adapter.push_menu(canonical_menu) via ChannelLink's adapter
           f. Store snapshot in MenuLocationChannel.snapshot
           g. Update status to "published" or "failed"

Step 5: Merchant edits menu (adds item, changes sort order)
        -> MenuLocationChannel.status remains "published" (now stale)
        -> UI shows "unpublished changes" indicator
        -> Merchant must re-publish for changes to go live
```

---

## Edge Cases

| Edge Case                                                      | How It's Handled                                                                                                                          |
|----------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| Product in menu but not stocked at a location                  | Skipped at publish time. No ProductLocation row = product doesn't exist at that location. Publish log warns: "3 items skipped (not stocked)." |
| ChannelLink is inactive                                        | MenuLocationChannel can't publish. Status stays "draft" or publish returns error.                                                         |
| Menu has no availability rows                                  | Always active. Empty MenuAvailability set means no time restrictions.                                                                     |
| Two menus with overlapping schedules at same location+channel  | Allowed. The channel platform handles which is active (takes latest push). Optionally add validation to warn about overlaps.              |
| Merchant deactivates a menu                                    | `Menu.is_active = False`. Doesn't auto-unpublish from channels — requires explicit unpublish action (or can be automated).                |
| Product deleted from catalog                                   | MenuItem cascade-deletes (FK to Product). Next publish reflects the removal.                                                              |
| Location removed from menu                                     | MenuLocation deleted -> cascades to MenuLocationChannel. Published menus become stale until channel is updated.                           |
| Modifier price differs per channel                             | Handled by existing ProductLocation.channels on the modifier's own ProductLocation row. Resolved at publish time.                         |
| Same product in two categories within one menu                 | Not allowed (Unique: menu, product). Matches delivery platform constraints. Can be relaxed to (menu_category, product) if needed later.   |

---

## Layer Responsibilities Summary

| Layer                         | Owns                                                                 | Does Not Own                                     |
|-------------------------------|----------------------------------------------------------------------|--------------------------------------------------|
| Merchant (accounts)           | Tenant identity                                                      | Product data, menus                              |
| Product Catalog (existing)    | Product data, base pricing, modifiers, categories, tax rates. **Core fields read-only when `managed_by` is an external POS slug (e.g. `"clover"`). Fully writable when `managed_by="internal_pos"` or `""`.** | Menu structure, scheduling, publishing           |
| ProductLocation (existing)    | Location stocking, location/channel pricing, availability, inventory. **Always writable (override layer).** | Menu curation                                    |
| Menu (new)                    | What items to show, in what structure, when (schedule), where (locations + channels). **Always writable (platform-owned).** | Pricing (delegates to catalog), availability toggles (delegates to catalog) |
| MenuLocationChannel (new)     | Publish state, snapshot of what was pushed                           | Credentials, external store ID (on ChannelLink)  |

The menu layer is **thin and referential** — it doesn't duplicate product data. It's purely about curation, structure, scheduling, and publishing. All the heavy lifting (pricing, tax, availability, modifiers) stays in the catalog layer.

---

## App Structure (New `menus` TENANT App)

```
menus/
+-- models/
|   +-- __init__.py              # Re-exports all models
|   +-- menu.py                  # Menu
|   +-- menu_category.py         # MenuCategory
|   +-- menu_item.py             # MenuItem
|   +-- menu_availability.py     # MenuAvailability
|   +-- menu_location.py         # MenuLocation
|   +-- menu_location_channel.py # MenuLocationChannel
+-- services/
|   +-- __init__.py
|   +-- menu_builder.py          # Add/remove items, duplicate menus
|   +-- menu_publisher.py        # Build canonical menu -> push via adapter
+-- serializers/
|   +-- __init__.py
|   +-- menu.py
|   +-- menu_item.py
|   +-- menu_publish.py
+-- views/
|   +-- __init__.py
|   +-- menu.py                  # MenuViewSet
+-- urls.py
+-- admin.py
+-- apps.py
```

## API Endpoints

```
# Menu CRUD (GET returns nested categories, items, availabilities, locations with channels)
GET/POST         /api/v1/menus/
GET/PATCH/DELETE  /api/v1/menus/{id}/

# Menu categories
POST             /api/v1/menus/{id}/categories/
PATCH/DELETE     /api/v1/menus/{id}/categories/{cat_id}/
PATCH            /api/v1/menus/{id}/categories/bulk/         # Bulk update (sort_order, name, etc.)

# Menu items (products in a menu)
POST             /api/v1/menus/{id}/items/
PATCH/DELETE     /api/v1/menus/{id}/items/{item_id}/
PATCH            /api/v1/menus/{id}/items/bulk/              # Bulk update (sort_order, price_override, etc.)
POST             /api/v1/menus/{id}/items/bulk-remove/       # Bulk remove items

# Availability windows
POST             /api/v1/menus/{id}/availabilities/
DELETE           /api/v1/menus/{id}/availabilities/{av_id}/

# Location assignments (uses X-Location-ID header instead of path params)
POST/DELETE      /api/v1/menus/{id}/locations/               # Header: X-Location-ID

# Channel assignments (uses X-Location-ID + X-Channel-Link-ID headers)
POST/DELETE      /api/v1/menus/{id}/channels/                # Headers: X-Location-ID, X-Channel-Link-ID

# Publishing
POST             /api/v1/menus/{id}/publish/
GET              /api/v1/menus/{id}/publish-status/

# Duplicate
POST             /api/v1/menus/{id}/duplicate/
```

> **Note:** Location and channel assignment use header-based context (X-Location-ID, X-Channel-Link-ID) rather than nested URL path parameters. This matches the pattern used by ProductViewSet and avoids drf-spectacular path parameter derivation warnings.
