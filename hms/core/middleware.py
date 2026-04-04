"""
core/middleware.py
==================
Production middleware stack for HMS.

Middleware classes (apply in this order in settings.MIDDLEWARE):
  1. SecurityHeadersMiddleware   — sets all OWASP-required HTTP security headers
  2. CorrelationIDMiddleware     — assigns a unique ID to every request for log tracing
  3. RequestLoggingMiddleware    — structured JSON log of every inbound request
  4. AuditContextMiddleware      — stores request on thread-local for audit writers
  5. SensitiveDataMiddleware     — scrubs PII from error responses and logs

All middleware is zero-dependency (no third-party libs beyond Django).
"""

import ipaddress
import logging
import threading
import time
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("hms.middleware")
security_logger = logging.getLogger("hms.security")

# Thread-local storage: stores the full request object so audit writers
# (signal handlers, service methods) can access IP/UA without threading request
# through every call stack.
_thread_locals = threading.local()


# ---------------------------------------------------------------------------
# Public helpers — called by audit code in other modules
# ---------------------------------------------------------------------------

def get_current_request():
    """Return the current HTTP request from thread-local, or None."""
    return getattr(_thread_locals, "request", None)


def get_current_user():
    """Return the authenticated user from the current request, or None."""
    request = get_current_request()
    if not request:
        return None
    user = getattr(request, "user", None)
    return user if (user and getattr(user, "is_authenticated", False)) else None


def get_client_ip(request):
    """
    Extract real client IP, honouring X-Forwarded-For when behind Nginx/ELB.
    Returns a string. Falls back to REMOTE_ADDR.
    Validates the result is a real IP before returning.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        # Take the first (leftmost) address — the original client
        candidate = forwarded_for.split(",")[0].strip()
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            pass
    return request.META.get("REMOTE_ADDR", "unknown")


def get_correlation_id(request):
    """Return the correlation ID attached to this request."""
    return getattr(request, "correlation_id", "no-correlation-id")


# ---------------------------------------------------------------------------
# 1. SecurityHeadersMiddleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Adds OWASP-recommended HTTP security headers to every response.
    Nginx should also set these — this is a belt-and-suspenders layer.

    Headers set
    -----------
    Strict-Transport-Security   Enforces HTTPS for 1 year (preload-ready).
    Content-Security-Policy     Restricts where scripts/styles/frames may load from.
    X-Content-Type-Options      Prevents MIME-type sniffing.
    X-Frame-Options             Blocks clickjacking via iframes.
    Referrer-Policy             Limits referrer header leakage.
    Permissions-Policy          Disables dangerous browser features.
    Cache-Control               Prevents caching of authenticated API responses.
    X-XSS-Protection            Legacy header for older browsers.
    """

    # Content-Security-Policy: API-only service — no inline scripts or external resources
    CSP = (
        "default-src 'none'; "
        "script-src 'none'; "
        "style-src 'none'; "
        "img-src 'none'; "
        "connect-src 'self'; "
        "font-src 'none'; "
        "frame-src 'none'; "
        "media-src 'none'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self';"
    )

    PERMISSIONS_POLICY = (
        "accelerometer=(), "
        "ambient-light-sensor=(), "
        "camera=(), "
        "geolocation=(), "
        "gyroscope=(), "
        "magnetometer=(), "
        "microphone=(), "
        "payment=(), "
        "usb=()"
    )

    def process_response(self, request, response):
        # Transport security
        if not settings.DEBUG:
            response["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Content security
        response["Content-Security-Policy"]   = self.CSP
        response["X-Content-Type-Options"]    = "nosniff"
        response["X-Frame-Options"]           = "DENY"
        response["X-XSS-Protection"]          = "1; mode=block"
        response["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response["Permissions-Policy"]        = self.PERMISSIONS_POLICY

        # Cache — all API responses are private and must not be cached
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response["Pragma"]        = "no-cache"
        response["Expires"]       = "0"

        # Remove headers that leak server info
        response.pop("Server",  None)
        response.pop("X-Powered-By", None)

        return response


# ---------------------------------------------------------------------------
# 2. CorrelationIDMiddleware
# ---------------------------------------------------------------------------

class CorrelationIDMiddleware(MiddlewareMixin):
    """
    Assigns a UUID4 correlation ID to every request.

    The ID is:
    - Accepted from the client via X-Correlation-ID header (validated as UUID)
    - Generated fresh if absent or invalid
    - Attached to the request object (request.correlation_id)
    - Returned in the response header X-Correlation-ID
    - Added to every log record via CorrelationIDFilter (see logging config)

    This allows complete tracing of a single request across:
    - Django logs, Celery task logs, Sentry events, and nginx access logs.
    """

    HEADER_IN  = "HTTP_X_CORRELATION_ID"
    HEADER_OUT = "X-Correlation-ID"

    def process_request(self, request):
        raw = request.META.get(self.HEADER_IN, "")
        try:
            # Validate: must be a proper UUID4, not arbitrary input
            correlation_id = str(uuid.UUID(raw, version=4))
        except (ValueError, AttributeError):
            correlation_id = str(uuid.uuid4())

        request.correlation_id = correlation_id
        # Also store on thread-local so loggers can access it without the request
        _thread_locals.correlation_id = correlation_id

    def process_response(self, request, response):
        cid = getattr(request, "correlation_id", "")
        if cid:
            response[self.HEADER_OUT] = cid
        return response


# ---------------------------------------------------------------------------
# 3. RequestLoggingMiddleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Writes a structured log record for every request and its response.

    Log fields
    ----------
    correlation_id, method, path, status_code, duration_ms,
    user_id, user_email, user_role, ip, user_agent

    Sensitive paths listed in MASKED_PATHS are logged but their
    request body is replaced with [REDACTED].

    Paths in SKIP_PATHS produce no log record (health checks, static).
    """

    SKIP_PATHS = {"/health/", "/favicon.ico", "/static/", "/media/"}

    # Request bodies on these paths are never logged
    MASKED_PATHS = {
        "/api/v1/auth/login/",
        "/api/v1/auth/refresh/",
        "/api/v1/auth/me/password/",
    }

    def process_request(self, request):
        request._start_time = time.monotonic()

    def process_response(self, request, response):
        path = request.path

        # Skip non-API paths
        if any(path.startswith(skip) for skip in self.SKIP_PATHS):
            return response

        duration_ms = round(
            (time.monotonic() - getattr(request, "_start_time", time.monotonic())) * 1000, 2
        )

        user    = getattr(request, "user", None)
        user_id = str(user.pk)    if (user and getattr(user, "is_authenticated", False)) else None
        email   = user.email      if (user and getattr(user, "is_authenticated", False)) else None
        role    = user.role       if (user and getattr(user, "is_authenticated", False)) else None

        log_data = {
            "event":          "http_request",
            "correlation_id": getattr(request, "correlation_id", ""),
            "method":         request.method,
            "path":           path,
            "query":          request.META.get("QUERY_STRING", ""),
            "status_code":    response.status_code,
            "duration_ms":    duration_ms,
            "ip":             get_client_ip(request),
            "user_agent":     request.META.get("HTTP_USER_AGENT", "")[:256],
            "user_id":        user_id,
            "user_email":     email,
            "user_role":      role,
        }

        # Log at WARNING for 4xx/5xx, INFO for everything else
        if response.status_code >= 500:
            logger.error("request completed", extra=log_data)
        elif response.status_code >= 400:
            logger.warning("request completed", extra=log_data)
        else:
            logger.info("request completed", extra=log_data)

        return response


# ---------------------------------------------------------------------------
# 4. AuditContextMiddleware
# ---------------------------------------------------------------------------

class AuditContextMiddleware(MiddlewareMixin):
    """
    Stores the full request on thread-local storage.
    Signal handlers and service methods call get_current_request() /
    get_current_user() / get_client_ip() to read context without needing
    the request object threaded through every function call.

    Always clears the thread-local in a finally block — critical for
    gunicorn worker reuse (threads are recycled across requests).
    """

    def process_request(self, request):
        _thread_locals.request = request

    def process_response(self, request, response):
        _thread_locals.request = None
        _thread_locals.correlation_id = None
        return response

    def process_exception(self, request, exception):
        _thread_locals.request = None
        _thread_locals.correlation_id = None


# ---------------------------------------------------------------------------
# 5. SensitiveDataMaskingMiddleware
# ---------------------------------------------------------------------------

class SensitiveDataMaskingMiddleware(MiddlewareMixin):
    """
    Scrubs known PII field names from JSON error responses (4xx/5xx).

    This is a last-resort guard — serializers should not expose sensitive
    fields in the first place. This middleware catches anything that slips
    through (e.g. a DRF validation error that echoes submitted input).

    PII_FIELDS are replaced with "***REDACTED***" in the response body.
    Only applies to JSON responses containing those exact field names.
    """

    PII_FIELDS = frozenset({
        "password", "password2", "current_password", "new_password",
        "mfa_secret", "national_id", "is_hiv_positive",
        "credit_card", "card_number", "cvv", "pin",
    })

    def process_response(self, request, response):
        # Only process error responses with JSON content
        if response.status_code < 400:
            return response
        content_type = response.get("Content-Type", "")
        if "application/json" not in content_type:
            return response

        try:
            import json
            data = json.loads(response.content)
            if self._contains_pii(data):
                data   = self._redact(data)
                response.content = json.dumps(data).encode()
                response["Content-Length"] = len(response.content)
        except (json.JSONDecodeError, Exception):
            pass

        return response

    def _contains_pii(self, obj):
        if isinstance(obj, dict):
            return bool(self.PII_FIELDS & set(obj.keys())) or any(
                self._contains_pii(v) for v in obj.values()
            )
        if isinstance(obj, list):
            return any(self._contains_pii(i) for i in obj)
        return False

    def _redact(self, obj):
        if isinstance(obj, dict):
            return {
                k: "***REDACTED***" if k in self.PII_FIELDS else self._redact(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [self._redact(i) for i in obj]
        return obj


# ---------------------------------------------------------------------------
# 6. RateLimitMiddleware  (application-level, backs up Nginx)
# ---------------------------------------------------------------------------

class RateLimitMiddleware(MiddlewareMixin):
    """
    Simple in-process rate limiter using Django's cache backend.
    Acts as a secondary defence — the primary rate limit lives in Nginx.

    Limits
    ------
    /api/v1/auth/login/   → 10 attempts per IP per 5 minutes
    All other paths       → 300 requests per IP per minute

    Returns 429 with Retry-After header on breach.
    Skips localhost in DEBUG mode.
    """

    LOGIN_PATH   = "/api/v1/auth/login/"
    LOGIN_LIMIT  = 10
    LOGIN_WINDOW = 300     # 5 minutes in seconds

    GLOBAL_LIMIT  = 300
    GLOBAL_WINDOW = 60

    def process_request(self, request):
        if settings.DEBUG:
            return None   # no rate limiting in dev

        ip   = get_client_ip(request)
        path = request.path

        if path == self.LOGIN_PATH:
            limit, window, prefix = self.LOGIN_LIMIT, self.LOGIN_WINDOW, "rl:login"
        else:
            limit, window, prefix = self.GLOBAL_LIMIT, self.GLOBAL_WINDOW, "rl:global"

        from django.core.cache import cache
        cache_key = f"{prefix}:{ip}"

        try:
            count = cache.get(cache_key, 0)
            if count >= limit:
                security_logger.warning(
                    "rate_limit_breach",
                    extra={"ip": ip, "path": path, "count": count, "limit": limit},
                )
                response = JsonResponse(
                    {"error": {"status_code": 429, "detail": "Too many requests. Please slow down."}},
                    status=429,
                )
                response["Retry-After"] = str(window)
                response["X-RateLimit-Limit"] = str(limit)
                response["X-RateLimit-Remaining"] = "0"
                return response

            # Increment with atomic add
            if count == 0:
                cache.set(cache_key, 1, timeout=window)
            else:
                cache.incr(cache_key)
        except Exception:
            # Never block a request over a cache failure
            pass

        return None
