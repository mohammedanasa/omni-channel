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
| Python             | 3.12 (inferred from `__pycache__` bytecode)       |

---

## Project Structure

```
django-auth/                   # Root
├── backend/                   # Django project package (settings, urls, wsgi)
│   ├── settings.py            # Main settings (shared/tenant apps, middleware, JWT, etc.)
│   ├── urls.py                # Root URL config → /api/v1/ entry point
│   ├── api_v1_urls.py         # V1 sub-router (auth, accounts, locations, products)
│   ├── asgi.py / wsgi.py
│   └── __init__.py
├── accounts/                  # SHARED app — Users, Merchants, Domains
│   ├── models.py              # User (custom, email-based), Merchant (TenantMixin), Domain
│   ├── views.py               # MerchantViewSet (CRUD, owner-scoped)
│   ├── serializers.py         # UserCreate, MerchantCreate/Update/Read serializers
│   ├── permissions.py         # IsMerchantOwner permission
│   ├── middleware.py          # TenantFromHeaderMiddleware (X-Tenant-ID header routing)
│   └── urls.py                # /merchants/ router
├── locations/                 # TENANT app — Physical store locations
│   ├── models.py              # Location (name, address, city, pincode)
│   ├── views.py               # LocationViewSet (tenant-scoped)
│   ├── serializers.py
│   └── urls.py                # /locations/ router
├── products/                  # TENANT app — Products, Categories, Tax Rates
│   ├── models.py              # TaxRate, Category, Product (+ ProductType enum), ProductRelation, ProductLocation
│   ├── views.py               # ProductViewSet, CategoryViewSet, TaxRateViewSet (custom actions: bulk_sync, export_menu, mark_unavailable)
│   ├── serializers.py         # Rich serializers with nested expand, location assignments, channel support
│   ├── admin.py               # Django admin registrations
│   └── urls.py                # /products/, /categories/, /tax-rates/ routers
├── helpers/
│   ├── common.py              # OpenAPI helpers (TENANT_HEADER, LOCATION_HEADER, @tenant_schema decorator)
│   └── permissions/
│       └── permissions.py     # HasTenantAccess permission
├── tests/
│   ├── base.py                # BaseAPITest (helper methods: create_user, authenticate, create_merchant, etc.)
│   ├── merchants/test_merchants.py
│   ├── locations/test_locations.py
│   └── products/test_products.py
├── manage.py
├── requirements.txt
├── pytest.ini
├── docker-compose.yml         # Postgres container (port 5434:5432)
├── schema.yml                 # Generated OpenAPI schema
├── .env                       # Local env config (DB creds, email backend)
└── .gitignore
```

---

## Django Apps & Tenancy

| App        | Type     | Description                                              |
| ---------- | -------- | -------------------------------------------------------- |
| `accounts` | SHARED   | Lives in **public** schema. Custom User, Merchant, Domain models. |
| `locations`| TENANT   | Lives in **per-tenant** schemas. Physical store locations. |
| `products` | TENANT   | Lives in **per-tenant** schemas. Products, Categories, Tax Rates, Product-Location assignments. |

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

## Development Commands

### Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy .env and configure DB credentials
# DB must be PostgreSQL (django-tenants requirement)
```

### Database
```bash
# Migrations (django-tenants uses migrate_schemas)
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
# IMPORTANT: The TenantMainMiddleware line in settings.py must remain COMMENTED OUT
# for tests to work. The custom TenantFromHeaderMiddleware is used instead.

# Run all tests
pytest -s

# Run a specific test file
pytest tests/products/test_products.py -s

# Run a specific test
pytest tests/products/test_products.py::TestProduct::test_create_product_with_nonexistent_category -s
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
| `EMAIL_HOST`       | `127.0.0.1`                               |                      |
| `EMAIL_PORT`       | `1025`                                    |                      |
| `EMAIL_USE_TLS`    | `False`                                   |                      |

---

## Important Notes

1. **Database must be PostgreSQL** — `django-tenants` requires PostgreSQL for schema-level isolation.
2. **Public tenant must exist** — After initial migration, create the public tenant via `manage.py shell` (see `commands.md` for the script).
3. **Middleware order matters** — `TenantFromHeaderMiddleware` must be the **first** middleware.
4. **Settings flags for testing** — `TENANT_TESTING = True` and `TESTING = True` are set in `settings.py` to prevent schema drop issues during tests.
5. **Product models are large** — `products/models.py` (~1800 lines), `products/views.py` (~1385 lines), `products/serializers.py` (~1859 lines) contain comprehensive POS product management with modifiers, bundles, location pricing, channel support, and tax calculations.
6. **Migrations are gitignored** — The `.gitignore` excludes all `migrations/` directories. You must run `makemigrations` locally.
7. **Schema file** — `schema.yml` is the pre-generated OpenAPI spec.
