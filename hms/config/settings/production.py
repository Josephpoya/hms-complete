"""
config/settings/production.py
==============================
Production hardening — applied on top of base.py.
"""
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from decouple import config
from .base import *  # noqa

DEBUG = False

# ---------------------------------------------------------------------------
# Transport security
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT             = True
SECURE_HSTS_SECONDS             = 31_536_000      # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
SECURE_HSTS_PRELOAD             = True
SECURE_PROXY_SSL_HEADER         = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE           = True
CSRF_COOKIE_SECURE              = True
CSRF_COOKIE_HTTPONLY            = True
SESSION_COOKIE_AGE              = 3600            # 1 hour session timeout

# ---------------------------------------------------------------------------
# Static/media via S3
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID        = config("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY    = config("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME  = config("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME       = config("AWS_S3_REGION_NAME", default="af-south-1")
AWS_DEFAULT_ACL          = "private"           # Never public
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
AWS_QUERYSTRING_AUTH     = True                # Always use presigned URLs
AWS_QUERYSTRING_EXPIRE   = 3600               # URLs expire in 1 hour
AWS_S3_FILE_OVERWRITE    = False              # Never silently overwrite files

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {"location": "media"},
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3boto3.S3ManifestStaticStorage",
        "OPTIONS": {"location": "static"},
    },
}

# ---------------------------------------------------------------------------
# Sentry — with PII scrubbing
# ---------------------------------------------------------------------------
sentry_sdk.init(
    dsn=config("SENTRY_DSN", default=""),
    integrations=[
        DjangoIntegration(transaction_style="url"),
        CeleryIntegration(),
        LoggingIntegration(
            level=None,          # capture log records as breadcrumbs
            event_level="ERROR", # send ERROR+ as Sentry events
        ),
    ],
    traces_sample_rate=0.05,     # 5% of transactions for performance
    profiles_sample_rate=0.01,
    send_default_pii=False,      # NEVER send PII to Sentry
    environment="production",
    before_send=_scrub_sentry_event,
)


def _scrub_sentry_event(event, hint):
    """Remove any PII that may have slipped into Sentry events."""
    _PII_KEYS = {"password", "mfa_secret", "national_id", "is_hiv_positive"}

    def scrub(obj):
        if isinstance(obj, dict):
            return {k: "***" if k in _PII_KEYS else scrub(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [scrub(i) for i in obj]
        return obj

    return scrub(event)


# ---------------------------------------------------------------------------
# DRF throttle rates — stricter in production
# ---------------------------------------------------------------------------
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon":  "10/minute",
    "user":  "100/minute",
    "login": "5/minute",
}

# ---------------------------------------------------------------------------
# Additional security: disallow browsable API entirely
# ---------------------------------------------------------------------------
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
]
