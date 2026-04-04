"""
notifications/tasks.py
=======================
Celery tasks for all HMS notifications.

Queue routing:
  notifications  — all outbound SMS and email
  reports        — report generation
  critical       — time-sensitive tasks (medication expiry alerts)
  default        — everything else

Retry strategy:
  SMS tasks retry 3 times with exponential backoff: 60s, 120s, 240s.
  This handles transient Africa's Talking API failures without losing messages.
"""

import logging
from datetime import timedelta
from typing import Optional

from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.utils import timezone

task_logger = get_task_logger(__name__)
logger = logging.getLogger("hms.notifications")


# ─── SMS: single message ──────────────────────────────────────────────────────
@shared_task(
    name="notifications.send_sms",
    queue="notifications",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,          # Message only acknowledged after task succeeds
    reject_on_worker_lost=True,
)
def send_sms_task(self, to: str, message: str, appointment_id: Optional[str] = None):
    """
    Send a single SMS.

    Parameters
    ----------
    to             : E.164 phone number (+256700000000)
    message        : Message text (max 160 chars per segment)
    appointment_id : Optional UUID for delivery log linkage

    Retry policy:
      Attempt 1 immediately, attempt 2 after 60s, attempt 3 after 120s, attempt 4 after 240s.
    """
    from notifications.sms_service import sms_service

    task_logger.info("Sending SMS to %s (attempt %d)", to, self.request.retries + 1)

    try:
        result = sms_service.send(to=to, message=message, appointment_id=appointment_id)
        if not result.success:
            raise Exception(f"SMS not sent: {result.error} (status={result.status})")
        task_logger.info("SMS sent: messageId=%s cost=%s", result.message_id, result.cost)
        return {"success": True, "message_id": result.message_id}

    except Exception as exc:
        task_logger.warning("SMS attempt %d failed: %s", self.request.retries + 1, exc)
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries),  # 60s, 120s, 240s
        )


# ─── Appointment reminder dispatcher ─────────────────────────────────────────
@shared_task(
    name="notifications.send_appointment_reminders",
    queue="notifications",
    bind=True,
    max_retries=2,
)
def send_appointment_reminders_task(self, hours_ahead: int = 24):
    """
    Find upcoming appointments without a sent reminder and dispatch SMS.

    Called by Celery Beat:
    - Every 30 minutes for 24-hour reminders
    - Every 15 minutes for 2-hour reminders

    Idempotent: reminder_sent_at acts as a guard flag.
    """
    from appointments.models import Appointment, AppointmentStatus
    from notifications.sms_service import sms_service, SMSTemplate

    window_start = timezone.now()
    window_end   = timezone.now() + timedelta(hours=hours_ahead)

    pending = (
        Appointment.objects
        .filter(
            status=AppointmentStatus.BOOKED,
            scheduled_at__gte=window_start,
            scheduled_at__lte=window_end,
            reminder_sent_at__isnull=True,
            patient__phone__isnull=False,
        )
        .select_related("patient", "doctor")
    )

    sent = 0
    failed = 0

    for appt in pending.iterator(chunk_size=50):
        phone = appt.patient.phone
        if not phone:
            continue

        try:
            message = SMSTemplate.appointment_reminder(appt)
            # Queue each SMS as an individual task for independent retry
            send_sms_task.delay(
                to=phone,
                message=message,
                appointment_id=str(appt.id),
            )
            # Mark reminder as sent to prevent duplicate sends
            appt.reminder_sent_at = timezone.now()
            appt.save(update_fields=["reminder_sent_at"])
            sent += 1

        except Exception as exc:
            logger.error("Failed to queue reminder for appt %s: %s", appt.id, exc)
            failed += 1

    task_logger.info(
        "Appointment reminders dispatched: sent=%d failed=%d window=%dh",
        sent, failed, hours_ahead,
    )
    return {"sent": sent, "failed": failed, "hours_ahead": hours_ahead}


# ─── Appointment confirmation ─────────────────────────────────────────────────
@shared_task(
    name="notifications.send_appointment_confirmation",
    queue="notifications",
    bind=True,
    max_retries=2,
)
def send_appointment_confirmation_task(self, appointment_id: str):
    """
    Send booking confirmation SMS immediately after an appointment is created.
    Called from the AppointmentViewSet.perform_create() via .delay().
    """
    from appointments.models import Appointment
    from notifications.sms_service import sms_service, SMSTemplate

    try:
        appt = (
            Appointment.objects
            .select_related("patient", "doctor")
            .get(pk=appointment_id)
        )
        if not appt.patient.phone:
            return {"skipped": "no phone number"}

        message = SMSTemplate.appointment_confirmation(appt)
        send_sms_task.delay(
            to=appt.patient.phone,
            message=message,
            appointment_id=appointment_id,
        )
        return {"queued": True, "to": appt.patient.phone}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


# ─── Invoice issued notification ──────────────────────────────────────────────
@shared_task(name="notifications.send_invoice_sms", queue="notifications", bind=True, max_retries=2)
def send_invoice_sms_task(self, invoice_id: str):
    """Send SMS to patient when an invoice is issued."""
    from billing.models import Invoice
    from notifications.sms_service import sms_service, SMSTemplate

    try:
        invoice = Invoice.objects.select_related("patient").get(pk=invoice_id)
        if not invoice.patient.phone:
            return {"skipped": "no phone number"}
        message = SMSTemplate.invoice_issued(invoice)
        send_sms_task.delay(to=invoice.patient.phone, message=message)
        return {"queued": True}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


# ─── Prescription ready notification ─────────────────────────────────────────
@shared_task(name="notifications.send_prescription_sms", queue="notifications", bind=True, max_retries=2)
def send_prescription_ready_task(self, prescription_id: str):
    """Send SMS when a prescription has been dispensed."""
    from pharmacy.models import Prescription
    from notifications.sms_service import sms_service, SMSTemplate

    try:
        rx = Prescription.objects.select_related("patient", "drug").get(pk=prescription_id)
        if not rx.patient.phone:
            return {"skipped": "no phone number"}
        message = SMSTemplate.prescription_ready(rx)
        send_sms_task.delay(to=rx.patient.phone, message=message)
        return {"queued": True}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


# ─── Low stock SMS to pharmacy manager ───────────────────────────────────────
@shared_task(name="notifications.alert_low_stock", queue="critical")
def alert_low_stock_task():
    """
    Run daily. Send SMS to pharmacy manager for each drug below reorder level.
    Manager phone is read from settings.HMS_PHARMACY_MANAGER_PHONE.
    """
    from pharmacy.models import Drug
    from notifications.sms_service import sms_service, SMSTemplate
    from django.db.models import F

    manager_phone = getattr(settings, "HMS_PHARMACY_MANAGER_PHONE", None)
    if not manager_phone:
        task_logger.warning("HMS_PHARMACY_MANAGER_PHONE not set — skipping low stock alerts")
        return

    low = Drug.objects.active().filter(stock_quantity__lte=F("reorder_level"))
    for drug in low:
        send_sms_task.delay(
            to=manager_phone,
            message=SMSTemplate.low_stock_alert(drug),
        )
    return {"alerts_queued": low.count()}


# ─── Bulk SMS (e.g. appointment changes affecting many patients) ───────────────
@shared_task(name="notifications.send_bulk_sms", queue="notifications", bind=True, max_retries=1)
def send_bulk_sms_task(self, recipients: list, message: str):
    """
    Send same message to many recipients.
    recipients: list of {"phone": "+256..."} dicts.
    Africa's Talking supports bulk sends in a single API call.
    """
    from notifications.sms_service import sms_service

    if not recipients:
        return {"sent": 0}

    # Process in batches of 100 (AT API limit per call)
    BATCH_SIZE = 100
    total_sent = 0
    for i in range(0, len(recipients), BATCH_SIZE):
        batch = recipients[i : i + BATCH_SIZE]
        results = sms_service.send_bulk(batch, message)
        total_sent += sum(1 for r in results if r.success)

    task_logger.info("Bulk SMS complete: %d/%d sent", total_sent, len(recipients))
    return {"sent": total_sent, "total": len(recipients)}
