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
8. **Shared utilities go in `common/`.** Base models (`BaseUUIDModel`), shared mixins, and cross-app utilities live in the `common` app.
9. **`@extend_schema_field` on every `SerializerMethodField`.** All `get_*` methods on serializers must have a `drf-spectacular` type annotation to avoid schema generation warnings.

### When to Split a File vs Keep It Flat

| File size          | Action                                                          |
| ------------------ | --------------------------------------------------------------- |
| < 300 lines        | **Stay flat** — single `models.py`, `views.py`, etc.            |
| 300–800 lines      | **Split selectively** — only split the oversized file           |
| 800+ lines         | **Full package split** — `models/`, `services/`, `serializers/`, `views/` |

---

## Project Structure

```
django-auth/                        # Root
├── backend/                        # Django project package
│   ├── settings.py                 # Settings (shared/tenant apps, middleware, JWT)
│   ├── urls.py                     # Root URL config → /api/v1/
│   ├── api_v1_urls.py              # V1 sub-router
│   ├── asgi.py / wsgi.py
│   └── __init__.py
│
├── common/                         # Shared utilities (NOT a Django app in INSTALLED_APPS)
│   ├── __init__.py
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
│   │   ├── __init__.py             # Re-exports: LocationSerializer
│   │   └── location.py
│   ├── views/
│   │   ├── __init__.py             # Re-exports: LocationViewSet
│   │   └── location.py
│   ├── permissions.py
│   ├── urls.py
│   └── admin.py
│
├── products/                       # TENANT app — Products, Categories, Tax Rates
│   ├── models/
│   │   ├── __init__.py             # Re-exports: Product, Category, TaxRate, ProductLocation, ProductRelation
│   │   ├── tax_rate.py             # TaxRate (percentage/flat-fee, auto-switch default)
│   │   ├── category.py             # Category (pos_category_id, sort_order)
│   │   ├── product.py              # Product + ProductType enum (imports TaxRate, Category)
│   │   ├── product_location.py     # ProductLocation junction (imports Product, TaxRate)
│   │   └── product_relation.py     # ProductRelation parent-child (imports Product)
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
│   │   ├── mixins.py               # HeaderContextMixin (_get_location/channel_from_header)
│   │   ├── constants.py            # CHANNEL_HEADER, PRODUCT_TYPE_FILTER (OpenAPI params)
│   │   ├── product.py              # ProductViewSet (thin — delegates to services)
│   │   ├── category.py             # CategoryViewSet
│   │   └── tax_rate.py             # TaxRateViewSet
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
│   └── products/test_products.py
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

| App        | Type     | Description                                              |
| ---------- | -------- | -------------------------------------------------------- |
| `accounts` | SHARED   | Lives in **public** schema. Custom User, Merchant, Domain models. |
| `locations`| TENANT   | Lives in **per-tenant** schemas. Physical store locations. |
| `products` | TENANT   | Lives in **per-tenant** schemas. Products, Categories, Tax Rates, Product-Location assignments. |
| `common`   | UTILITY  | Not in INSTALLED_APPS. Shared abstract models (BaseUUIDModel). |

**Tenant model:** `accounts.Merchant` (extends `TenantMixin`)
**Domain model:** `accounts.Domain` (extends `DomainMixin`)

---

## Key Architectural Patterns

### Multi-Tenancy via Header (not subdomain)
- `TENANT_SUBDOMAIN_BASED_ROUTING = False`
- Custom middleware `accounts.middleware.TenantFromHeaderMiddleware` reads `X-Tenant-ID` header
- Routes requiring tenant data (`/products/`, `/categories/`, `/tax-rates/`, `/locations/`) **reject** requests without `X-Tenant-ID`
- Public-schema routes (auth, merchants) work without the header

### Authentication Flow
1. Register: `POST /api/v1/auth/users/` (Djoser)
2. Login: `POST /api/v1/auth/jwt/create/` → returns `access` + `refresh` tokens
3. All subsequent requests: `Authorization: Bearer <access_token>`

### Custom Headers
| Header          | Purpose                                      | Required |
| --------------- | -------------------------------------------- | -------- |
| `Authorization` | JWT Bearer token                             | Yes      |
| `X-Tenant-ID`   | Merchant UUID → switches DB schema           | For tenant endpoints |
| `X-Location-ID`  | Location UUID → scopes/filters by location  | Optional |
| `X-Channel`      | Channel name (e.g. `ubereats`, `doordash`)  | Optional |

### Product Types (enum)
| Value | Type           | Description                              |
| ----- | -------------- | ---------------------------------------- |
| 1     | MAIN           | Sellable products (burgers, drinks)      |
| 2     | MODIFIER_ITEM  | Individual options (lettuce, cheese)     |
| 3     | MODIFIER_GROUP | Container for modifier items             |
| 4     | BUNDLE_GROUP   | Container for bundle options (combos)    |

### Model Dependency Graph (products app)
```
common/models.py (BaseUUIDModel)
       ↓
tax_rate.py ──────────────────┐
                              │
category.py ──────┐           │
                  ▼           ▼
              product.py  (imports TaxRate, Category)
                  │
                  ▼
          product_location.py  (imports Product, TaxRate)
          product_relation.py  (imports Product)
```
No circular imports. Each file imports only from files "above" it. `product.py` uses lazy imports for `ProductLocation` inside methods to avoid circular dependency.

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

### Locations (tenant schema — requires `X-Tenant-ID`)
- `GET/POST locations/`
- `GET/PUT/PATCH/DELETE locations/{id}/`

### Products (tenant schema — requires `X-Tenant-ID`)
- `GET/POST products/` — List/Create (supports `?product_type=`, `?category_id=`)
- `GET/PUT/PATCH/DELETE products/{plu}/` — By PLU lookup
- `POST products/bulk_sync/` — Bulk upsert
- `GET products/export_menu/` — Export menu
- `POST products/mark_unavailable/` — Mark products unavailable
- `PATCH products/{plu}/update_location_pricing/` — Update location pricing
- `POST products/bulk_delete/` — Bulk delete by PLUs

### Categories (tenant schema)
- `GET/POST categories/`
- `GET/PUT/PATCH/DELETE categories/{pos_category_id}/`

### Tax Rates (tenant schema)
- `GET/POST tax-rates/`
- `GET/PUT/PATCH/DELETE tax-rates/{id}/`

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
2. Register app in `settings.py` under `SHARED_APPS` or `TENANT_APPS`
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
| `DB_ENGINE`        | `django_tenants.postgresql_backend`       | Required for tenants |
| `DB_NAME`          | `omni_channel_db`                         | Postgres DB name     |
| `DB_USER`          | `omni_channel_admin`                      | Postgres user        |
| `DB_PASSWORD`      | *(set locally)*                           | Postgres password    |
| `DB_HOST`          | `localhost`                               | Postgres host        |
| `DB_PORT`          | `5432`                                    | Postgres port        |
| `EMAIL_BACKEND`    | `django.core.mail.backends.console.EmailBackend` | Console in dev |

---

## Important Notes

1. **Database must be PostgreSQL** — `django-tenants` requires PostgreSQL for schema-level isolation.
2. **Public tenant must exist** — After initial migration, create the public tenant via `manage.py shell`.
3. **Middleware order matters** — `TenantFromHeaderMiddleware` must be the **first** middleware.
4. **Settings flags for testing** — `TENANT_TESTING = True` and `TESTING = True` are set in `settings.py`.
5. **Migrations are gitignored** — `.gitignore` excludes `migrations/` directories. Run `makemigrations` locally.
6. **Re-export everything split modules expose.** When splitting `models.py` → `models/`, the `__init__.py` must re-export all classes referenced by migrations, serializers, views, or other apps. Forgetting a re-export (e.g., `UserManager`) breaks migrations.
7. **Lazy imports for circular dependencies.** Within split model packages, if Model A references Model B and vice versa, use lazy imports inside methods (`from .b import B`) rather than top-level imports.
8. **Schema file** — `schema.yml` is the pre-generated OpenAPI spec.
