from datetime import timedelta

from .base import *  # noqa: F401, F403

DEBUG = True

# Development-specific settings
ALLOWED_HOSTS = ["*"]

# Console email backend for local development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Longer token lifetimes for convenience during development
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=120),
}

# Testing flags
TENANT_TESTING = True
TESTING = True

# ── CORS (Development) ──
# Allow the Vite dev server to make API requests
CORS_ALLOW_ALL_ORIGINS = True  # Dev only — production uses explicit origins
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "x-csrftoken",
    "x-requested-with",
    # Custom headers used by the multi-tenant API
    "x-tenant-id",
    "x-location-id",
    "x-channel",
    "x-channel-link-id",
]
