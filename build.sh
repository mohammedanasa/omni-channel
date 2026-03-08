#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

# Generate migrations (they are gitignored)
python manage.py makemigrations accounts locations products channels integrations orders webhooks

python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant
