## Create new database

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create database
CREATE DATABASE omni_channel_db;

# Create user with password
CREATE USER omni_channel_admin WITH PASSWORD 'C@licut3';

# Grant privileges
GRANT ALL PRIVILEGES ON DATABASE omni_channel_db TO omni_channel_admin;

# Change owner
ALTER DATABASE omni_channel_db  OWNER TO omni_channel_admin;

# Exit
\q
```

## Delete Database
```bash
DROP DATABASE database_name WITH (FORCE);
```

## DB Users
```bash
# List users
\du

# Delete user
DROP USER username;
```

## Migrations


```bash
# Create migrations
python manage.py makemigrations

# Run migrations for shared apps (public schema)
python manage.py migrate_schemas --shared

# Or migrate everything
python manage.py migrate_schemas

# Run migrations for tenant apps (tenant schemas)
python manage.py migrate_schemas --tenant

```

## Create Public Tenant (Required for django-tenants)

```bash
python manage.py shell
from django_tenants.utils import get_tenant_model, get_tenant_domain_model
from django.contrib.auth import get_user_model

TenantModel = get_tenant_model()
DomainModel = get_tenant_domain_model()


User = get_user_model()

# Get all superusers
superusers = User.objects.filter(is_superuser=True)

# Create public tenant
public_tenant = TenantModel(
    schema_name='public',
    name='Public',
    owner=superusers.first() if superusers.exists() else None
)
public_tenant.save()

# Create domain for public tenant
domain = DomainModel(
    domain='127.0.0.1',  # or your domain
    tenant=public_tenant,
    is_primary=True
)
domain.save()

print("Public tenant created!")
exit()
```