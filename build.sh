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
