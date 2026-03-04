from datetime import timedelta
from pathlib import Path
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-0t$lb0*xalq=40di6p@msbfew!9agtwf535q)qo_*ea-9qve9h"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


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
    ]
    
# INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]
INSTALLED_APPS = SHARED_APPS + TENANT_APPS


MIDDLEWARE = [
    # "django_tenants.middleware.main.TenantMainMiddleware",

    "accounts.middleware.TenantFromHeaderMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


#------------------ THIRD PARTY SETTINGS ------------------#
AUTH_USER_MODEL = "accounts.User"

#EMAIL CONFIGURATION
EMAIL_BACKEND = config("EMAIL_BACKEND")
EMAIL_HOST = config("EMAIL_HOST")
EMAIL_PORT = config("EMAIL_PORT", cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", cast=bool)

#REST FRAMEWORK CONFIGURATION
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

#DJOSER CONFIGURATION
DJOSER = {
    "LOGIN_FIELD": "email",
    "USER_CREATE_PASSWORD_RETYPE": True,
    "USERNAME_CHANGED_EMAIL_CONFIRMATION": True,
    "PASSWORD_CHANGED_EMAIL_CONFIRMATION": True,
    "SEND_CONFIRMATION_EMAIL": True,
    "PASSWORD_RESET_CONFIRM_URL": "password/reset/confirm/{uid}/{token}",
    "USERNAME_RESET_CONFIRM_URL": "email/reset/confirm/{uid}/{token}",
    "ACTIVATION_URL": "activate/{uid}/{token}",
    "SEND_ACTIVATION_EMAIL": True,
    "PASSWORD_RESET_SHOW_EMAIL_NOT_FOUND": True,
    "SERIALIZERS": {
        "user_create": "accounts.serializers.UserCreateSerializer",
        # "user": "accounts.serializers.UserCreateSerializer",
        # "user_delete": "djoser.serializers.UserDeleteSerializer",
    },
}

DOMAIN="localhost:3000"
SITE_NAME="Auth System"

def capitalize_tags(endpoints, **kwargs):
    """Capitalize auto-generated tags (e.g. 'auth' → 'Auth')."""
    for path, path_regex, method, callback in endpoints:
        if hasattr(callback, 'cls'):
            # Check if the view already has explicit tags via @extend_schema
            pass  # drf-spectacular handles tag generation later
    return endpoints


def postprocess_capitalize_tags(result, generator, request, public):
    """Post-process the schema to capitalize all tag names."""
    tag_map = {}
    for path_data in result.get('paths', {}).values():
        for operation in path_data.values():
            if isinstance(operation, dict) and 'tags' in operation:
                operation['tags'] = [
                    tag.title() if tag.islower() else tag
                    for tag in operation['tags']
                ]
    # Also update the top-level tags list
    if 'tags' in result:
        for tag_obj in result['tags']:
            if tag_obj.get('name', '').islower():
                tag_obj['name'] = tag_obj['name'].title()
    return result


SPECTACULAR_SETTINGS = {
    "TITLE": "POS System API",
    "DESCRIPTION": "API documentation for the Django Auth System project.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    'SCHEMA_PATH_PREFIX': r'/api/v[0-9]',
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
        'backend.settings.postprocess_capitalize_tags',
    ],
    # ReDoc specific settings can be passed here
    'REDOC_UI_SETTINGS': {
        'hideDownloadButton': True,
        'expandResponses': '200,201',
    },
}




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

DATABASE_ROUTERS = (
    "django_tenants.routers.TenantSyncRouter",
)

TENANT_SUBDOMAIN_BASED_ROUTING = False
TENANT_MODEL = "accounts.Merchant"  # app.Model
TENANT_DOMAIN_MODEL = "accounts.Domain"  # app.Model
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

TENANT_TESTING = True  # prevents schema drop issues in tests
TESTING = True
