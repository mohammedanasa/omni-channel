from datetime import timedelta
from pathlib import Path
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY", default="django-insecure-0t$lb0*xalq=40di6p@msbfew!9agtwf535q)qo_*ea-9qve9h")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=lambda v: [h.strip() for h in v.split(",") if h.strip()] if v else [])

RENDER_EXTERNAL_HOSTNAME = config("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

ALLOWED_HOSTS.append("127.0.0.1")

# Application definition

SHARED_APPS = [
    "django_tenants",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third Party Apps
    "rest_framework",
    "djoser",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "rest_framework.authtoken",
    "corsheaders",
    "accounts",
    "channels",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "django_extensions",
]

TENANT_APPS = [
    "locations",
    "products",
    "integrations",
    "orders",
    "webhooks",
    "menus",
]

INSTALLED_APPS = SHARED_APPS + TENANT_APPS


MIDDLEWARE = [
    "accounts.middleware.TenantFromHeaderMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ──────────────────── THIRD PARTY SETTINGS ──────────────────── #
AUTH_USER_MODEL = "accounts.User"

# EMAIL CONFIGURATION
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

# REST FRAMEWORK CONFIGURATION
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}

# DJOSER CONFIGURATION
DJOSER = {
    "LOGIN_FIELD": "email",
    "USER_CREATE_PASSWORD_RETYPE": True,
    "USERNAME_CHANGED_EMAIL_CONFIRMATION": True,
    "PASSWORD_CHANGED_EMAIL_CONFIRMATION": True,
    "SEND_CONFIRMATION_EMAIL": False,
    "PASSWORD_RESET_CONFIRM_URL": "password/reset/confirm/{uid}/{token}",
    "USERNAME_RESET_CONFIRM_URL": "email/reset/confirm/{uid}/{token}",
    "ACTIVATION_URL": "activate/{uid}/{token}",
    "SEND_ACTIVATION_EMAIL": False,
    "PASSWORD_RESET_SHOW_EMAIL_NOT_FOUND": True,
    "SERIALIZERS": {
        "user_create": "accounts.serializers.UserCreateSerializer",
    },
}

DOMAIN = "localhost:3000"
SITE_NAME = "Auth System"


def postprocess_capitalize_tags(result, generator, request, public):
    """Post-process the schema to capitalize all tag names."""
    for path_data in result.get('paths', {}).values():
        for operation in path_data.values():
            if isinstance(operation, dict) and 'tags' in operation:
                operation['tags'] = [
                    tag.title() if tag.islower() else tag
                    for tag in operation['tags']
                ]
    if 'tags' in result:
        for tag_obj in result['tags']:
            if tag_obj.get('name', '').islower():
                tag_obj['name'] = tag_obj['name'].title()
    return result


SPECTACULAR_SETTINGS = {
    "TITLE": "Omni Channel API",
    "DESCRIPTION": "API documentation for the Omni channel project.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    'SCHEMA_PATH_PREFIX': r'/api/v[0-9]',
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
        'backend.settings.base.postprocess_capitalize_tags',
    ],
    'ENUM_NAME_OVERRIDES': {
        'OrderStatusEnum': 'orders.models.OrderStatus',
        'SyncStatusEnum': 'integrations.models.SyncStatus',
        'PublishStatusEnum': 'menus.models.menu_location_channel.PublishStatus',
    },
    'REDOC_UI_SETTINGS': {
        'hideDownloadButton': True,
        'expandResponses': '200,201',
    },
}


# DATABASE
DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": config("DB_NAME", default=BASE_DIR / "db.sqlite3"),
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default=""),
        "PORT": config("DB_PORT", default=""),
    }
}

if config("DB_SSLMODE", default=""):
    DATABASES["default"]["OPTIONS"] = {
        "sslmode": config("DB_SSLMODE"),
    }

DATABASE_ROUTERS = (
    "django_tenants.routers.TenantSyncRouter",
)

TENANT_SUBDOMAIN_BASED_ROUTING = False
TENANT_MODEL = "accounts.Merchant"
TENANT_DOMAIN_MODEL = "accounts.Domain"
PUBLIC_SCHEMA_NAME = "public"

# General Email Settings
DEFAULT_FROM_EMAIL = 'noreply@mydjangosystem.com'
SERVER_EMAIL = 'support@mydjangosystem.com'

# ── Celery ──
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
