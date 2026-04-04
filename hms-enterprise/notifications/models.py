"""
notifications/models.py
========================
SMS delivery log — immutable record of every message sent.
"""
import uuid
from django.db import models
from django.utils import timezone


class SMSLog(models.Model):
    """
    Append-only log of every SMS dispatched by the HMS.

    Provides:
    - Delivery receipt tracking (status updated via Africa's Talking webhook)
    - Cost accounting per message
    - Audit trail linking messages to appointments
    """
    STATUS_CHOICES = [
        ("sent",      "Sent"),
        ("delivered", "Delivered"),
        ("failed",    "Failed"),
        ("expired",   "Expired"),
        ("rejected",  "Rejected"),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient  = models.CharField(max_length=30)
    message    = models.TextField(max_length=500)
    provider   = models.CharField(max_length=50, default="africastalking")
    message_id = models.CharField(max_length=100, blank=True, db_index=True,
                                  help_text="Provider's message ID for delivery receipt matching")
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default="sent", db_index=True)
    cost       = models.CharField(max_length=20, blank=True)
    error      = models.TextField(blank=True)

    # Optional link to the appointment that triggered this message
    appointment_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at   = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_smslog"
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["recipient", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"SMS → {self.recipient} [{self.status}] at {self.created_at:%Y-%m-%d %H:%M}"
