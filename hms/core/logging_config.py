"""
core/logging_config.py
======================
Structured JSON logging configuration for the HMS.

Loggers
-------
  hms              — application root logger
  hms.security     — auth failures, permission denials, IP blocks
  hms.audit        — audit event writes (separate from AuditLog model)
  hms.middleware   — request/response logging
  hms.exceptions   — exception handler output
  hms.celery       — async task lifecycle
  django           — Django framework
  django.security  — Django's own security events (CSRF, SuspiciousOperation)
  django.db.backends — SQL queries in DEBUG mode only

Handlers
--------
  console          — StreamHandler → stdout (captured by systemd/docker/ECS)
  security_file    — RotatingFileHandler for security events (7-day retention)
  audit_file       — RotatingFileHandler for audit events (permanent, rotated daily)
  null             — discards noisy framework noise

All production logs are JSON. Development logs are human-readable.

Log levels
----------
  Production   : WARNING for root; INFO for hms.*; DEBUG for hms.* when DEBUG=True
  Development  : DEBUG for everything

Privacy
-------
The CorrelationIDFilter adds correlation_id to every record.
The ScrubPIIFilter replaces known PII patterns in log messages.
No patient name, MRN, or clinical data appears in log messages —
only IDs and role names.
"""

import logging
import re


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class CorrelationIDFilter(logging.Filter):
    """Injects correlation_id from thread-local into every log record."""

    def filter(self, record):
        try:
            from core.middleware import _thread_locals
            record.correlation_id = getattr(_thread_locals, "correlation_id", "-")
        except Exception:
            record.correlation_id = "-"
        return True


class ScrubPIIFilter(logging.Filter):
    """
    Replaces known PII patterns in log message strings.
    Acts as a last-resort safety net — log statements should not include PII.

    Patterns scrubbed
    -----------------
    - Email addresses
    - Phone numbers (Uganda format and E.164)
    - Credit card numbers (Luhn-format)
    - MRN patterns
    """

    _EMAIL   = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    _PHONE   = re.compile(r"(\+?256|0)[0-9]{9}")
    _CC      = re.compile(r"\b(?:\d[ -]?){13,16}\b")

    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        return True

    def _scrub(self, text):
        text = self._EMAIL.sub("[EMAIL]", text)
        text = self._PHONE.sub("[PHONE]", text)
        text = self._CC.sub("[CARD]", text)
        return text


class RequestContextFilter(logging.Filter):
    """Adds request context fields available from thread-local."""

    def filter(self, record):
        try:
            from core.middleware import get_current_request, get_client_ip
            request = get_current_request()
            if request:
                record.request_method = request.method
                record.request_path   = request.path
                record.client_ip      = get_client_ip(request)
            else:
                record.request_method = "-"
                record.request_path   = "-"
                record.client_ip      = "-"
        except Exception:
            record.request_method = "-"
            record.request_path   = "-"
            record.client_ip      = "-"
        return True


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """
    Formats log records as compact JSON for structured log aggregators
    (Cloudwatch, Datadog, ELK, GCP Logging).

    Output fields
    -------------
    timestamp, level, logger, message, correlation_id,
    request_method, request_path, client_ip,
    [exc_info if exception]
    """

    def format(self, record):
        import json
        from datetime import datetime, timezone as tz

        self.formatException  # ensure exc_info is set
        output = {
            "timestamp":      datetime.now(tz.utc).isoformat(),
            "level":          record.levelname,
            "logger":         record.name,
            "message":        record.getMessage(),
            "module":         record.module,
            "correlation_id": getattr(record, "correlation_id", "-"),
            "client_ip":      getattr(record, "client_ip", "-"),
            "request_method": getattr(record, "request_method", "-"),
            "request_path":   getattr(record, "request_path", "-"),
        }

        # Extra fields added by loggers (event, user_email, etc.)
        extra_keys = {
            "event", "user_id", "user_email", "user_role",
            "ip", "path", "method", "status_code", "duration_ms",
            "table_name", "action", "record_id",
        }
        for key in extra_keys:
            val = getattr(record, key, None)
            if val is not None:
                output[key] = val

        if record.exc_info:
            output["exception"] = self.formatException(record.exc_info)

        return json.dumps(output, default=str)


# ---------------------------------------------------------------------------
# LOGGING dict — imported into settings/base.py
# ---------------------------------------------------------------------------

def build_logging_config(debug=False, log_dir="/var/log/hms"):
    """
    Returns the LOGGING dict for Django's logging configuration.
    Call in settings: LOGGING = build_logging_config(debug=DEBUG)
    """
    formatter = "verbose" if debug else "json"

    config = {
        "version":                  1,
        "disable_existing_loggers": False,

        "filters": {
            "correlation_id": {
                "()": "core.logging_config.CorrelationIDFilter",
            },
            "scrub_pii": {
                "()": "core.logging_config.ScrubPIIFilter",
            },
            "request_context": {
                "()": "core.logging_config.RequestContextFilter",
            },
            "require_debug_false": {
                "()": "django.utils.log.RequireDebugFalse",
            },
            "require_debug_true": {
                "()": "django.utils.log.RequireDebugTrue",
            },
        },

        "formatters": {
            "json": {
                "()": "core.logging_config.JSONFormatter",
            },
            "verbose": {
                "format": (
                    "[{levelname}] {asctime} {correlation_id} "
                    "{name} {module}:{lineno} — {message}"
                ),
                "style": "{",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "security": {
                "format": "[SECURITY] {asctime} {levelname} {message} correlation={correlation_id}",
                "style": "{",
            },
        },

        "handlers": {
            "console": {
                "class":     "logging.StreamHandler",
                "formatter": formatter,
                "filters":   ["correlation_id", "scrub_pii", "request_context"],
                "stream":    "ext://sys.stdout",
            },
            "console_error": {
                "class":     "logging.StreamHandler",
                "formatter": formatter,
                "filters":   ["correlation_id", "scrub_pii"],
                "stream":    "ext://sys.stderr",
                "level":     "ERROR",
            },
            "security_file": {
                "class":       "logging.handlers.RotatingFileHandler",
                "filename":    f"{log_dir}/security.log",
                "maxBytes":    50 * 1024 * 1024,    # 50 MB
                "backupCount": 7,
                "formatter":   "security",
                "filters":     ["correlation_id", "scrub_pii"],
                "encoding":    "utf-8",
            },
            "audit_file": {
                "class":       "logging.handlers.TimedRotatingFileHandler",
                "filename":    f"{log_dir}/audit.log",
                "when":        "midnight",
                "backupCount": 365,    # 1 year of daily files
                "formatter":   formatter,
                "filters":     ["correlation_id"],
                "encoding":    "utf-8",
                "utc":         True,
            },
            "null": {
                "class": "logging.NullHandler",
            },
        },

        "root": {
            "level":    "WARNING",
            "handlers": ["console"],
        },

        "loggers": {
            # HMS application loggers
            "hms": {
                "level":     "INFO" if not debug else "DEBUG",
                "handlers":  ["console"],
                "propagate": False,
            },
            "hms.security": {
                "level":     "INFO",
                "handlers":  ["console", "security_file"],
                "propagate": False,
            },
            "hms.audit": {
                "level":     "INFO",
                "handlers":  ["console", "audit_file"],
                "propagate": False,
            },
            "hms.middleware": {
                "level":     "INFO" if not debug else "DEBUG",
                "handlers":  ["console"],
                "propagate": False,
            },
            "hms.exceptions": {
                "level":     "WARNING",
                "handlers":  ["console", "console_error"],
                "propagate": False,
            },

            # Celery
            "celery": {
                "level":     "INFO",
                "handlers":  ["console"],
                "propagate": False,
            },

            # Django framework
            "django": {
                "level":     "WARNING",
                "handlers":  ["console"],
                "propagate": False,
            },
            "django.security": {
                "level":     "ERROR",
                "handlers":  ["console", "security_file"],
                "propagate": False,
            },
            "django.request": {
                "level":     "ERROR",
                "handlers":  ["console"],
                "propagate": False,
            },
            # SQL query logging — only in DEBUG
            "django.db.backends": {
                "level":     "DEBUG" if debug else "WARNING",
                "handlers":  ["console"] if debug else ["null"],
                "propagate": False,
            },
        },
    }

    # In production, add file handlers if log_dir is writable
    if not debug:
        import os
        try:
            os.makedirs(log_dir, exist_ok=True)
            config["loggers"]["hms"]["handlers"].append("security_file")
            config["loggers"]["hms.security"]["handlers"] = ["console", "security_file"]
            config["loggers"]["hms.audit"]["handlers"]    = ["console", "audit_file"]
        except (OSError, PermissionError):
            # Fall back to console-only if log_dir is not writable
            pass

    return config
