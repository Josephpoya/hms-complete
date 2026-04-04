"""
config/settings/base.py
=======================
Shared settings for all environments.
All sensitive values read from environment variables via python-decouple.
"""
import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY    = config("SECRET_KEY")
DEBUG         = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
]

LOCAL_APPS = [
    "core",
    "accounts",
    "patients",
    "doctors",
    "appointments",
    "billing",
    "pharmacy",
    "records",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware — ORDER IS CRITICAL
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    # 1. Rate limiting — reject before any processing
    "core.middleware.RateLimitMiddleware",
    # 2. Security headers on every response
    "core.middleware.SecurityHeadersMiddleware",
    # 3. Correlation ID — must be before logging
    "core.middleware.CorrelationIDMiddleware",
    # 4. Django security
    "django.middleware.security.SecurityMiddleware",
    # 5. CORS — before CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # 6. Audit context — must be before auth so signals have request access
    "core.middleware.AuditContextMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # 7. Request logging — after auth so user is populated
    "core.middleware.RequestLoggingMiddleware",
    # 8. PII scrubbing — last, on responses
    "core.middleware.SensitiveDataMaskingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS":    [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
import dj_database_url

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=60,
        conn_health_checks=True,
        ssl_require=not DEBUG,
    )
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE     = "Africa/Kampala"
USE_I18N      = True
USE_TZ        = True

# ---------------------------------------------------------------------------
# Static / Media
# ---------------------------------------------------------------------------
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL   = "/media/"
MEDIA_ROOT  = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardResultsPagination",
    "PAGE_SIZE":                25,
    "DEFAULT_SCHEMA_CLASS":     "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER":        "core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon":  "20/minute",
        "user":  "200/minute",
        "login": "5/minute",
    },
    # Security: hide browsable API in production (only JSON renderer is set above)
    # No BrowsableAPIRenderer in DEFAULT_RENDERER_CLASSES.
}

# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS":  True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN":      True,
    "ALGORITHM":              "HS256",
    "SIGNING_KEY":            SECRET_KEY,
    "AUTH_HEADER_TYPES":      ("Bearer",),
    "USER_ID_FIELD":          "id",
    "USER_ID_CLAIM":          "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "accounts.serializers.CustomTokenObtainPairSerializer",
    "TOKEN_BLACKLIST_ENABLED": True,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS  = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv())
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept", "accept-encoding", "authorization",
    "content-type", "dnt", "origin", "user-agent",
    "x-csrftoken", "x-requested-with", "x-correlation-id",
]
CORS_EXPOSE_HEADERS = ["X-Correlation-ID"]

# ---------------------------------------------------------------------------
# Security flags (hardened further in production.py)
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS             = "DENY"

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_ENGINE          = "django.contrib.sessions.backends.cache"

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND":  "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/0"),
        "KEY_PREFIX": "hms",
        "TIMEOUT":  300,
        "OPTIONS":  {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL          = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND      = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT      = ["json"]
CELERY_TASK_SERIALIZER     = "json"
CELERY_RESULT_SERIALIZER   = "json"
CELERY_TIMEZONE            = TIME_ZONE
CELERY_BEAT_SCHEDULER      = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_TRACK_STARTED  = True
CELERY_TASK_TIME_LIMIT     = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND       = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST          = config("EMAIL_HOST", default="localhost")
EMAIL_PORT          = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL  = config("DEFAULT_FROM_EMAIL", default="noreply@hospital.com")

# ---------------------------------------------------------------------------
# Logging — structured JSON in production, readable in dev
# ---------------------------------------------------------------------------
from core.logging_config import build_logging_config
LOGGING = build_logging_config(debug=DEBUG, log_dir=config("LOG_DIR", default="/var/log/hms"))

# ---------------------------------------------------------------------------
# DRF Spectacular
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE":                  "Hospital Management System API",
    "DESCRIPTION":            "Production HMS REST API — JWT authenticated, RBAC enforced.",
    "VERSION":                "1.0.0",
    "SERVE_INCLUDE_SCHEMA":   False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX":     r"/api/v1/",
    "SERVE_PERMISSIONS":      ["rest_framework.permissions.IsAdminUser"],
}

# ---------------------------------------------------------------------------
# HMS application constants
# ---------------------------------------------------------------------------
HMS_MRN_PREFIX              = "MRN"
HMS_INVOICE_PREFIX          = "INV"
HMS_MAX_LOGIN_ATTEMPTS      = 5
HMS_ACCOUNT_LOCKOUT_MINUTES = 30
HMS_AUDIT_RETENTION_YEARS   = 7
HMS_RECORD_LOCK_HOURS       = 24    # Medical records lock after this many hours
HMS_PRESCRIPTION_EXPIRY_DAYS = 30   # Default prescription validity
