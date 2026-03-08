#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

# Generate migrations only for installed apps (they are gitignored)
APPS=$(python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from django.apps import apps
candidates = ['accounts','locations','products','channels','integrations','orders','webhooks']
print(' '.join(a for a in candidates if apps.is_installed(a)))
")
python manage.py makemigrations $APPS

python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant

# Create superuser if it doesn't already exist
python manage.py shell -c "
from accounts.models import User
if not User.objects.filter(email='$DJANGO_SUPERUSER_EMAIL').exists():
    User.objects.create_superuser(
        email='$DJANGO_SUPERUSER_EMAIL',
        password='$DJANGO_SUPERUSER_PASSWORD',
        first_name='Admin'
    )
    print('Superuser created')
else:
    print('Superuser already exists')
"

# Create public tenant if it doesn't already exist
python manage.py shell -c "
from django_tenants.utils import get_tenant_model, get_tenant_domain_model
from django.contrib.auth import get_user_model

TenantModel = get_tenant_model()
DomainModel = get_tenant_domain_model()
User = get_user_model()

if not TenantModel.objects.filter(schema_name='public').exists():
    owner = User.objects.filter(is_superuser=True).first()
    public_tenant = TenantModel(schema_name='public', name='Public', owner=owner)
    public_tenant.save()
    DomainModel(domain='$RENDER_EXTERNAL_HOSTNAME', tenant=public_tenant, is_primary=True).save()
    print('Public tenant created')
else:
    print('Public tenant already exists')
"
