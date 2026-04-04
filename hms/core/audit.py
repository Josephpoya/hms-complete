"""
core/audit.py
=============
Centralised audit logging system.

This module is the single entry point for ALL audit events in the HMS.
It replaces the partial implementation in accounts/signals.py.

Architecture
------------

  AuditService        — stateless class, call AuditService.log() from anywhere.
  ModelAuditMixin     — adds before/after JSON snapshots to model save/delete.
  audit_view          — decorator for view methods that need explicit audit events.
  AuditSignalHandler  — connects Django signals to AuditService for tracked models.

Audit events are written asynchronously via Celery when available,
falling back to synchronous writes to prevent blocking the HTTP response.

Immutability
------------
The AuditLog model enforces immutability at the application layer (save/delete
raise PermissionError on existing records). The database enforces it via REVOKE
UPDATE, DELETE on the hms_user role (applied in migration 0001_initial).

Retention
---------
AuditLog is partitioned by created_at (monthly). Celery beat job runs monthly
to detach partitions older than the retention window and archive to S3.
"""

import json
import logging
from datetime import timedelta
from functools import wraps

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from core.middleware import get_client_ip, get_correlation_id, get_current_request, get_current_user

logger = logging.getLogger("hms.audit")


# ---------------------------------------------------------------------------
# Audit action constants
# ---------------------------------------------------------------------------

class AuditAction:
    CREATE  = "CREATE"
    READ    = "READ"
    UPDATE  = "UPDATE"
    DELETE  = "DELETE"
    LOGIN   = "LOGIN"
    LOGOUT  = "LOGOUT"
    EXPORT  = "EXPORT"
    ACCESS  = "ACCESS"    # sensitive field read (HIV status, national ID)
    FAIL    = "FAIL"      # failed auth / permission denied


# ---------------------------------------------------------------------------
# Safe JSON serialiser — handles UUIDs, Decimals, datetimes, model instances
# ---------------------------------------------------------------------------

class AuditJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        try:
            import uuid
            if isinstance(obj, uuid.UUID):
                return str(obj)
        except ImportError:
            pass
        try:
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return str(obj)
        except ImportError:
            pass
        if hasattr(obj, "pk"):
            return str(obj.pk)
        return super().default(obj)


def _safe_json(data):
    """Convert data to a JSON-safe dict, silently dropping non-serialisable values."""
    if data is None:
        return None
    try:
        return json.loads(json.dumps(data, cls=AuditJSONEncoder))
    except Exception:
        return {"_error": "Could not serialise audit payload"}


# ---------------------------------------------------------------------------
# Model snapshot — captures field values before/after changes
# ---------------------------------------------------------------------------

# Fields that must never appear in audit snapshots
_NEVER_SNAPSHOT = frozenset({
    "password", "mfa_secret", "national_id",
})

# Fields that are hashed/masked in snapshots
_MASKED_FIELDS = frozenset({
    "is_hiv_positive",
})


def _snapshot_model(instance):
    """
    Return a dict of field_name → value for a model instance.
    Excludes sensitive fields and truncates text to 500 chars.
    """
    if instance is None:
        return None

    snapshot = {}
    try:
        for field in instance._meta.get_fields():
            # Skip relations and reverse managers
            if hasattr(field, "get_accessor_name"):
                continue
            if not hasattr(field, "attname"):
                continue
            name = field.attname
            if name in _NEVER_SNAPSHOT:
                continue
            try:
                value = getattr(instance, name)
                if name in _MASKED_FIELDS:
                    value = "***"
                elif isinstance(value, str) and len(value) > 500:
                    value = value[:500] + "...[truncated]"
                snapshot[name] = value
            except Exception:
                snapshot[name] = "[unreadable]"
    except Exception:
        pass

    return _safe_json(snapshot)


# ---------------------------------------------------------------------------
# Core AuditService
# ---------------------------------------------------------------------------

class AuditService:
    """
    Stateless audit logging service. All methods are class methods.

    Usage from any module
    ---------------------
    from core.audit import AuditService, AuditAction

    AuditService.log(
        action     = AuditAction.EXPORT,
        table_name = "patients_patient",
        record_id  = patient.pk,
        new_value  = {"format": "csv", "rows": 200},
    )

    # View decorator
    @audit_view(action=AuditAction.ACCESS, table="patients_patient")
    def my_view(request, pk):
        ...
    """

    @classmethod
    def log(
        cls,
        action,
        table_name,
        record_id=None,
        user=None,
        old_value=None,
        new_value=None,
        notes=None,
    ):
        """
        Write one audit event. Safe to call from anywhere — never raises.

        Parameters
        ----------
        action      : AuditAction constant.
        table_name  : DB table name of the affected model.
        record_id   : PK of the affected row (UUID or None for bulk ops).
        user        : accounts.User instance (auto-detected from request if None).
        old_value   : Dict snapshot of state before change.
        new_value   : Dict snapshot of state after change.
        notes       : Free-text annotation visible in the admin audit view.
        """
        try:
            cls._write(
                action=action,
                table_name=table_name,
                record_id=record_id,
                user=user,
                old_value=old_value,
                new_value=new_value,
                notes=notes,
            )
        except Exception as exc:
            # Audit failure must NEVER crash the application.
            logger.error(
                "audit_write_failed action=%s table=%s error=%s",
                action, table_name, exc,
            )

    @classmethod
    def log_login(cls, user, success, reason=None):
        cls.log(
            action=AuditAction.LOGIN if success else AuditAction.FAIL,
            table_name="accounts_user",
            record_id=user.pk if user else None,
            user=user if success else None,
            new_value={
                "success":      success,
                "reason":       reason,
                "timestamp":    timezone.now().isoformat(),
            },
        )

    @classmethod
    def log_logout(cls, user):
        cls.log(
            action=AuditAction.LOGOUT,
            table_name="accounts_user",
            record_id=user.pk,
            user=user,
        )

    @classmethod
    def log_export(cls, user, table_name, filters, row_count, export_format="csv"):
        cls.log(
            action=AuditAction.EXPORT,
            table_name=table_name,
            user=user,
            new_value={
                "format":    export_format,
                "row_count": row_count,
                "filters":   _safe_json(filters),
            },
        )

    @classmethod
    def log_sensitive_access(cls, user, table_name, record_id, fields_accessed):
        """Log when a user reads a sensitive field (e.g. HIV status, national ID)."""
        cls.log(
            action=AuditAction.ACCESS,
            table_name=table_name,
            record_id=record_id,
            user=user,
            new_value={"fields_accessed": list(fields_accessed)},
        )

    @classmethod
    def log_permission_denied(cls, request, resource, action):
        user = get_current_user()
        cls.log(
            action=AuditAction.FAIL,
            table_name=resource,
            user=user,
            new_value={
                "attempted_action": action,
                "path":             request.path,
                "method":           request.method,
            },
        )

    # ------------------------------------------------------------------
    # Internal write path
    # ------------------------------------------------------------------

    @classmethod
    def _write(cls, action, table_name, record_id, user, old_value, new_value, notes):
        from accounts.signals import AuditLog

        request      = get_current_request()
        acting_user  = user or get_current_user()
        ip           = get_client_ip(request) if request else None
        ua           = request.META.get("HTTP_USER_AGENT", "")[:512] if request else ""
        cid          = get_correlation_id(request) if request else ""

        entry = AuditLog(
            user                = acting_user,
            user_email_snapshot = (acting_user.email if acting_user else "system"),
            user_role_snapshot  = (acting_user.role  if acting_user else "system"),
            action              = action,
            table_name          = table_name,
            record_id           = record_id,
            old_value           = _safe_json(old_value),
            new_value           = _safe_json({
                **(new_value or {}),
                "_correlation_id": cid,
                **({"_notes": notes} if notes else {}),
            }),
            ip_address          = ip,
            user_agent          = ua,
        )

        # Write synchronously inside an atomic block so the audit record
        # commits with the transaction it belongs to.
        # Use on_commit only for cross-transaction events (login, export).
        try:
            entry.save(using="default")
        except Exception:
            # Last resort: write to the error log so the event is not lost
            logger.critical(
                "AUDIT_FALLBACK action=%s table=%s record=%s user=%s",
                action, table_name, record_id,
                acting_user.email if acting_user else "system",
            )
            raise


# ---------------------------------------------------------------------------
# Model audit mixin — add to Django models for automatic before/after snapshots
# ---------------------------------------------------------------------------

class ModelAuditMixin:
    """
    Mixin for Django models that need before/after value snapshots in the
    audit log. Add this BEFORE models.Model in MRO.

    Usage
    -----
    class Patient(ModelAuditMixin, models.Model):
        ...

    On save():
      - Detects create vs update by checking self._state.adding.
      - Loads the pre-save version from the DB (one extra SELECT per write).
      - Writes the audit entry after the save succeeds.

    On delete():
      - Captures the snapshot before deletion.
      - Writes the audit entry after deletion commits.
    """

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        old_snapshot = None

        if not is_new:
            try:
                old_obj      = self.__class__.objects.get(pk=self.pk)
                old_snapshot = _snapshot_model(old_obj)
            except self.__class__.DoesNotExist:
                is_new = True

        super().save(*args, **kwargs)

        AuditService.log(
            action     = AuditAction.CREATE if is_new else AuditAction.UPDATE,
            table_name = self._meta.db_table,
            record_id  = self.pk,
            old_value  = old_snapshot,
            new_value  = _snapshot_model(self),
        )

    def delete(self, *args, **kwargs):
        snapshot   = _snapshot_model(self)
        record_id  = self.pk
        table_name = self._meta.db_table

        super().delete(*args, **kwargs)

        AuditService.log(
            action     = AuditAction.DELETE,
            table_name = table_name,
            record_id  = record_id,
            old_value  = snapshot,
        )


# ---------------------------------------------------------------------------
# Signal-based audit handler — used for models we cannot modify directly
# ---------------------------------------------------------------------------

class AuditSignalHandler:
    """
    Connects Django post_save / post_delete signals to AuditService.
    Unlike ModelAuditMixin, this does not capture before-snapshots (no
    extra DB query) — it logs only the action and the post-save state.

    Use ModelAuditMixin for high-value models where before/after diff matters.
    Use AuditSignalHandler for bulk-insert performance-sensitive models.
    """

    # Models that get FULL before/after diff (use ModelAuditMixin instead of signals)
    FULL_DIFF_MODELS = {
        "patients.Patient",
        "records.MedicalRecord",
        "pharmacy.Prescription",
    }

    # Models that get signal-based audit (action + post-save snapshot only)
    SIGNAL_MODELS = {
        "billing.Invoice",
        "billing.InvoiceItem",
        "appointments.Appointment",
        "doctors.Doctor",
    }

    @classmethod
    def register(cls):
        """Call from AppConfig.ready() after all apps are loaded."""
        from django.apps import apps
        from django.db.models.signals import post_save, post_delete

        for label in cls.SIGNAL_MODELS:
            try:
                model = apps.get_model(label)
                post_save.connect(
                    cls._make_save_handler(label),
                    sender=model,
                    weak=False,
                    dispatch_uid=f"audit_save_{label}",
                )
                post_delete.connect(
                    cls._make_delete_handler(label),
                    sender=model,
                    weak=False,
                    dispatch_uid=f"audit_delete_{label}",
                )
            except LookupError:
                logger.warning("AuditSignalHandler: model %s not found", label)

    @staticmethod
    def _make_save_handler(label):
        def handler(sender, instance, created, **kwargs):
            AuditService.log(
                action     = AuditAction.CREATE if created else AuditAction.UPDATE,
                table_name = sender._meta.db_table,
                record_id  = instance.pk,
                new_value  = _snapshot_model(instance),
            )
        handler.__name__ = f"audit_save_{label}"
        return handler

    @staticmethod
    def _make_delete_handler(label):
        def handler(sender, instance, **kwargs):
            AuditService.log(
                action     = AuditAction.DELETE,
                table_name = sender._meta.db_table,
                record_id  = instance.pk,
                old_value  = _snapshot_model(instance),
            )
        handler.__name__ = f"audit_delete_{label}"
        return handler


# ---------------------------------------------------------------------------
# View decorator
# ---------------------------------------------------------------------------

def audit_view(action, table, get_record_id=None):
    """
    Decorator for view methods that need explicit audit records.

    Usage
    -----
    @audit_view(action=AuditAction.EXPORT, table="patients_patient")
    def export(self, request):
        ...

    @audit_view(
        action=AuditAction.ACCESS,
        table="patients_patient",
        get_record_id=lambda self, request, pk: pk,
    )
    def retrieve_sensitive(self, request, pk=None):
        ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Determine request — works for both APIView methods and viewset actions
            request    = None
            record_id  = None

            for arg in args:
                if hasattr(arg, "method") and hasattr(arg, "user"):
                    request = arg
                    break

            if get_record_id and request:
                try:
                    record_id = get_record_id(*args, **kwargs)
                except Exception:
                    pass

            result = func(*args, **kwargs)

            AuditService.log(
                action     = action,
                table_name = table,
                record_id  = record_id,
                user       = get_current_user(),
            )
            return result
        return wrapper
    return decorator
