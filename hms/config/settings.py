"""
HMS Django Settings
===================
Production-ready configuration using python-decouple for environment
variable management. Never commit secrets — use a .env file locally
and your secrets manager (Vault / AWS Secrets Manager) in production.

Environment variables required in production:
  SECRET_KEY, DATABASE_URL, REDIS_URL, ALLOWED_HOSTS,
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME,
  FIELD_ENCRYPTION_KEY
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# Security
# ─────────────────────────────────────────────────────────────────────────────
SECRET_KEY = config("SECRET_KEY")

DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Field-level encryption key (Fernet) — required for PII columns
FIELD_ENCRYPTION_KEY = config("FIELD_ENCRYPTION_KEY")

# ─────────────────────────────────────────────────────────────────────────────
# Application Definition
# ─────────────────────────────────────────────────────────────────────────────
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
    "auditlog",
    "storages",
]

LOCAL_APPS = [
    "accounts",
    "patients",
    "doctors",
    "appointments",
    "billing",
    "pharmacy",
    "records",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─────────────────────────────────────────────────────────────────────────────
# Middleware  (order matters — CORS must come before CommonMiddleware)
# ─────────────────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",          # CORS — must be high up
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "auditlog.middleware.AuditlogMiddleware",         # Attaches request user to audit
]

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

# ─────────────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

# ─────────────────────────────────────────────────────────────────────────────
# Database — PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────
import dj_database_url  # noqa: E402

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL", default="postgres://hms_user:hms_pass@localhost:5432/hms_db"),
        conn_max_age=60,          # Persistent connections — 60 second keepalive
        conn_health_checks=True,  # Validate connection before reuse
    )
}

# Read replica for heavy report queries (optional — set in production)
# DATABASES["replica"] = dj_database_url.config(
#     env="DATABASE_REPLICA_URL",
#     conn_max_age=60,
# )

# ─────────────────────────────────────────────────────────────────────────────
# Custom Auth User Model
# ─────────────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"

# ─────────────────────────────────────────────────────────────────────────────
# Password Validation + Hashing
# ─────────────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2id — winner of the Password Hashing Competition; OWASP recommended
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",  # Fallback for migration
]

# ─────────────────────────────────────────────────────────────────────────────
# Django REST Framework
# ─────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    # All endpoints require authentication by default — explicitly opt out where needed
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        # BrowsableAPI only in DEBUG — remove for production hardening
        *(["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Throttling — prevents brute-force and abuse
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute",
        "user": "200/minute",
    },
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
}

# ─────────────────────────────────────────────────────────────────────────────
# SimpleJWT Configuration
# ─────────────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    # Short-lived access token — forces regular refresh, limits exposure window
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    # Refresh token — longer lived, stored securely by client
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    # Rotate refresh token on every use — one-time use tokens
    "ROTATE_REFRESH_TOKENS": True,
    # Blacklist old refresh tokens after rotation (requires token_blacklist app)
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    # Custom token serializer that embeds role + mfa_verified into JWT payload
    "TOKEN_OBTAIN_SERIALIZER": "accounts.serializers.HMSTokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSerializer",
}

# ─────────────────────────────────────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True  # Allow cookies / Authorization header

# ─────────────────────────────────────────────────────────────────────────────
# Cache — Redis
# ─────────────────────────────────────────────────────────────────────────────
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "hms",
        "TIMEOUT": 300,  # 5 minutes default TTL
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Celery — Async Task Queue
# ─────────────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = config("REDIS_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = "django-db"           # Store results in PostgreSQL
CELERY_CACHE_BACKEND = "default"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60             # Hard kill after 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60        # Raise SoftTimeLimitExceeded first
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ─────────────────────────────────────────────────────────────────────────────
# Storage — S3 (active in production; local filesystem in dev)
# ─────────────────────────────────────────────────────────────────────────────
USE_S3 = config("USE_S3", default=False, cast=bool)

if USE_S3:
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="af-south-1")
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_S3_SIGNATURE_VERSION = "s3v4"

    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"

# ─────────────────────────────────────────────────────────────────────────────
# Static Files
# ─────────────────────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# ─────────────────────────────────────────────────────────────────────────────
# Internationalisation
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"               # All DB timestamps stored as UTC
USE_I18N = True
USE_TZ = True                   # ALWAYS True — critical for TIMESTAMPTZ correctness

# ─────────────────────────────────────────────────────────────────────────────
# Default Primary Key
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.UUIDField"
# Note: each model explicitly sets primary_key=True with UUIDField + default=uuid.uuid4

# ─────────────────────────────────────────────────────────────────────────────
# DRF Spectacular — OpenAPI / Swagger
# ─────────────────────────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "Hospital Management System API",
    "DESCRIPTION": "Production API for HMS — patients, appointments, billing, pharmacy, records.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"BearerAuth": []}],
}

# ─────────────────────────────────────────────────────────────────────────────
# Security Headers (enforced by SecurityMiddleware in production)
# ─────────────────────────────────────────────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ─────────────────────────────────────────────────────────────────────────────
# Logging — Structured JSON in production, readable in dev
# ─────────────────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "structlog.stdlib.ProcessorFormatter",
            "processor": "structlog.dev.ConsoleRenderer" if DEBUG else "structlog.processors.JSONRenderer",
        },
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if not DEBUG else "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
        "hms": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False},
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# django-auditlog
# ─────────────────────────────────────────────────────────────────────────────
AUDITLOG_INCLUDE_ALL_MODELS = False   # Opt-in per model via @auditlog.register
AUDITLOG_EXCLUDE_TRACKING_FIELDS = ("updated_at",)
