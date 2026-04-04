"""
core/exceptions.py
==================
Centralised exception handling for the HMS API.

Goals
-----
1. Every API error returns the same JSON envelope — never raw HTML tracebacks.
2. 5xx errors are logged with full traceback + correlation ID, but the client
   sees only a generic message (no internal details leak).
3. 4xx errors include actionable, field-specific messages for the frontend.
4. Django ValidationError and DRF ValidationError are normalised to the same shape.
5. Sentry receives 5xx events with full context; 4xx events are filtered out
   (they are client errors, not server bugs).

Response envelope
-----------------
{
  "error": {
    "status_code": 422,
    "code":        "validation_error",
    "detail":      { "field_name": ["Error message."] },
    "request_id":  "3f4e8b2a-..."
  }
}
"""

import logging
import traceback

from django.conf import settings
from django.core.exceptions import (
    PermissionDenied as DjangoPermissionDenied,
    ValidationError as DjangoValidationError,
    ObjectDoesNotExist,
)
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
    NotFound,
    Throttled,
    MethodNotAllowed,
    UnsupportedMediaType,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.middleware import get_correlation_id, get_current_request

logger          = logging.getLogger("hms.exceptions")
security_logger = logging.getLogger("hms.security")


# ---------------------------------------------------------------------------
# Error code mapping
# ---------------------------------------------------------------------------

ERROR_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limit_exceeded",
    500: "internal_server_error",
    503: "service_unavailable",
}

# DRF exception class → error code override
EXCEPTION_CODE_MAP = {
    "NotAuthenticated":     "authentication_required",
    "AuthenticationFailed": "authentication_failed",
    "PermissionDenied":     "permission_denied",
    "NotFound":             "not_found",
    "ValidationError":      "validation_error",
    "Throttled":            "rate_limit_exceeded",
    "MethodNotAllowed":     "method_not_allowed",
}


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def _build_error_response(status_code, detail, code=None, request=None):
    """Build the standard error envelope."""
    error_code = code or ERROR_CODES.get(status_code, "error")
    request_id = ""
    if request:
        request_id = get_correlation_id(request)
    elif get_current_request():
        request_id = get_correlation_id(get_current_request())

    payload = {
        "error": {
            "status_code": status_code,
            "code":        error_code,
            "detail":      detail,
            "request_id":  request_id,
        }
    }
    return Response(payload, status=status_code)


def _normalise_detail(detail):
    """
    Normalise DRF's detail field (str | list | dict) into a consistent shape.
    Always returns either a string or a dict of field → list[str].
    """
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        # Flatten list of ErrorDetail to list of strings
        return [str(d) for d in detail]
    if isinstance(detail, dict):
        return {
            k: [str(e) for e in (v if isinstance(v, list) else [v])]
            for k, v in detail.items()
        }
    return str(detail)


# ---------------------------------------------------------------------------
# Main exception handler (registered in settings.REST_FRAMEWORK)
# ---------------------------------------------------------------------------

def custom_exception_handler(exc, context):
    """
    Global DRF exception handler.

    Handles
    -------
    - All DRF APIException subclasses
    - Django Http404, PermissionDenied
    - Django ValidationError (from model.full_clean())
    - Unhandled exceptions → 500

    Never exposes stack traces or internal paths to clients.
    Always logs with correlation ID.
    """
    request = context.get("request")
    view    = context.get("view")

    # ------------------------------------------------------------------
    # Step 1: Convert non-DRF exceptions to DRF exceptions
    # ------------------------------------------------------------------
    if isinstance(exc, Http404):
        exc = NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        # Convert Django's ValidationError → DRF's ValidationError
        if hasattr(exc, "message_dict"):
            exc = ValidationError(exc.message_dict)
        elif hasattr(exc, "messages"):
            exc = ValidationError(exc.messages)
        else:
            exc = ValidationError(str(exc))
    elif isinstance(exc, ObjectDoesNotExist):
        exc = NotFound(f"The requested resource was not found.")

    # ------------------------------------------------------------------
    # Step 2: Let DRF handle known APIExceptions
    # ------------------------------------------------------------------
    response = drf_exception_handler(exc, context)

    if response is not None:
        status_code = response.status_code
        exc_name    = type(exc).__name__
        code        = EXCEPTION_CODE_MAP.get(exc_name, ERROR_CODES.get(status_code, "error"))
        detail      = _normalise_detail(response.data)

        # Log security-relevant events
        if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
            security_logger.warning(
                "auth_failure path=%s code=%s correlation_id=%s",
                getattr(request, "path", "unknown"),
                code,
                get_correlation_id(request) if request else "",
            )
        elif isinstance(exc, PermissionDenied):
            security_logger.warning(
                "permission_denied path=%s user=%s correlation_id=%s",
                getattr(request, "path", "unknown"),
                getattr(getattr(request, "user", None), "email", "anonymous"),
                get_correlation_id(request) if request else "",
            )
        elif isinstance(exc, Throttled):
            security_logger.warning(
                "rate_limited path=%s wait=%ss",
                getattr(request, "path", "unknown"),
                exc.wait,
            )
        elif status_code >= 500:
            logger.error(
                "server_error status=%s path=%s view=%s correlation_id=%s",
                status_code,
                getattr(request, "path", "unknown"),
                view.__class__.__name__ if view else "unknown",
                get_correlation_id(request) if request else "",
                exc_info=True,
            )

        return _build_error_response(status_code, detail, code=code, request=request)

    # ------------------------------------------------------------------
    # Step 3: Unhandled exception → 500
    # ------------------------------------------------------------------
    correlation_id = get_correlation_id(request) if request else "no-request"
    tb = traceback.format_exc()

    logger.critical(
        "unhandled_exception view=%s path=%s correlation_id=%s\n%s",
        view.__class__.__name__ if view else "unknown",
        getattr(request, "path", "unknown"),
        correlation_id,
        tb,
    )

    # Send to Sentry in production
    if not settings.DEBUG:
        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("correlation_id", correlation_id)
                scope.set_tag("path", getattr(request, "path", "unknown"))
                if request and hasattr(request, "user"):
                    scope.set_user({"email": getattr(request.user, "email", "anonymous")})
                sentry_sdk.capture_exception(exc)
        except Exception:
            pass

    # Return generic 500 — no internal details exposed to client
    return _build_error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An internal server error occurred. Our team has been notified. "
        f"Reference ID: {correlation_id}",
        code="internal_server_error",
        request=request,
    )


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------

class BusinessRuleError(APIException):
    """
    Raised when a business rule is violated (not a validation error, not a bug).
    Examples: booking beyond doctor capacity, dispensing expired drug.
    Returns 422 Unprocessable Entity.
    """
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "business_rule_violation"
    default_detail = "A business rule prevented this operation."


class ResourceLockedError(APIException):
    """Raised when attempting to modify a locked resource (e.g. locked MedicalRecord)."""
    status_code = status.HTTP_423_LOCKED
    default_code = "resource_locked"
    default_detail = "This resource is locked and cannot be modified."


class DataIntegrityError(APIException):
    """Raised when an operation would violate data integrity constraints."""
    status_code = status.HTTP_409_CONFLICT
    default_code = "data_integrity_error"
    default_detail = "This operation conflicts with existing data."


class ServiceUnavailableError(APIException):
    """Raised when an external service (S3, email) is unreachable."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "service_unavailable"
    default_detail = "A required service is temporarily unavailable. Please try again."


class AuditWriteError(Exception):
    """
    Raised when an audit log entry cannot be written.
    This is critical — it must never silently fail in production.
    Caught by AuditService.log() which logs to the error logger as a fallback.
    """
    pass
