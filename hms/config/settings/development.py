"""
config/settings/development.py
================================
Development overrides — never use in production.
"""
from .base import *  # noqa

DEBUG             = True
ALLOWED_HOSTS     = ["*"]
EMAIL_BACKEND     = "django.core.mail.backends.console.EmailBackend"

# Relax throttling for local dev
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon":  "1000/minute",
    "user":  "1000/minute",
    "login": "100/minute",
}

# Show SQL queries
LOGGING["loggers"]["django.db.backends"]["level"] = "DEBUG"

# Add browsable API in dev for easy testing
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Debug toolbar (optional)
try:
    import debug_toolbar  # noqa
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass
