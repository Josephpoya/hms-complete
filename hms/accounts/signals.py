"""
accounts/signals.py
===================
AuditLog model + backwards-compatible signal registration.

AuditLog model lives here (accounts app) because it references accounts.User.
All signal registration logic has moved to core/audit.py.

Import write_audit and AuditAction from core.audit for new code.
"""
import uuid

from django.db import models
from django.db.models.signals import post_save, post_delete
from django.utils import timezone


class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Create"
    READ   = "READ",   "Read"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    LOGIN  = "LOGIN",  "Login"
    LOGOUT = "LOGOUT", "Logout"
    EXPORT = "EXPORT", "Export"
    ACCESS = "ACCESS", "Access"
    FAIL   = "FAIL",   "Fail"


class AuditLog(models.Model):
    """
    Append-only audit event log.

    Immutability contract:
      - save()   raises PermissionError if the record already exists.
      - delete() always raises PermissionError.
      - DB user (hms_user) has UPDATE and DELETE revoked (migration 0001).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        "accounts.User",
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
    )
    user_email_snapshot = models.CharField(max_length=255)
    user_role_snapshot  = models.CharField(max_length=30)

    action     = models.CharField(max_length=20, choices=AuditAction.choices, db_index=True)
    table_name = models.CharField(max_length=80, db_index=True)
    record_id  = models.UUIDField(null=True, blank=True, db_index=True)

    old_value  = models.JSONField(null=True, blank=True)
    new_value  = models.JSONField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        db_table = "audit_auditlog"
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["user_id", "created_at"],   name="idx_audit_user_ts"),
            models.Index(fields=["table_name", "record_id"],  name="idx_audit_table_rec"),
            models.Index(fields=["action", "created_at"],    name="idx_audit_action_ts"),
        ]

    def __str__(self):
        return f"{self.action} on {self.table_name} by {self.user_email_snapshot} at {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionError("AuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("AuditLog entries cannot be deleted.")


# ---------------------------------------------------------------------------
# Backwards-compatible helpers (delegate to core.audit)
# ---------------------------------------------------------------------------

def write_audit(action, table_name, record_id=None, user=None, old_value=None, new_value=None):
    """Backwards-compatible shim. Use core.audit.AuditService.log() in new code."""
    try:
        from core.audit import AuditService
        AuditService.log(
            action=action, table_name=table_name,
            record_id=record_id, user=user,
            old_value=old_value, new_value=new_value,
        )
    except Exception:
        pass


def register_audit_signals():
    """Backwards-compatible shim. Signal registration now happens in core/apps.py."""
    from core.audit import AuditSignalHandler
    AuditSignalHandler.register()
