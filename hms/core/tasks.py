"""
core/tasks.py
=============
Celery tasks for security-critical background jobs.

Tasks
-----
  lock_old_medical_records    — locks EHR records older than HMS_RECORD_LOCK_HOURS
  expire_old_prescriptions    — marks pending prescriptions past their expiry date
  check_drug_expiry           — alerts on drugs expiring within 30 days
  check_low_stock             — alerts on drugs at or below reorder level
  mark_overdue_invoices       — marks issued invoices past their due date as overdue
  archive_audit_logs          — (stub) archives old audit partitions to S3
  send_appointment_reminders  — sends SMS/email reminders for upcoming appointments
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("hms.celery")


# ---------------------------------------------------------------------------
# Medical record locking
# ---------------------------------------------------------------------------

@shared_task(
    name="core.lock_old_medical_records",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
)
def lock_old_medical_records(self):
    """
    Lock all unlocked medical records older than HMS_RECORD_LOCK_HOURS (default 24h).
    Runs every hour via Celery Beat.
    """
    try:
        from records.models import MedicalRecord

        lock_before = timezone.now() - timedelta(
            hours=getattr(settings, "HMS_RECORD_LOCK_HOURS", 24)
        )
        pending = MedicalRecord.objects.filter(
            is_locked=False,
            recorded_at__lte=lock_before,
        )
        count = 0
        for record in pending.iterator(chunk_size=100):
            try:
                record.lock()
                count += 1
            except Exception as exc:
                logger.error("Failed to lock record %s: %s", record.pk, exc)

        logger.info("lock_old_medical_records locked=%d", count)
        return {"locked": count}
    except Exception as exc:
        logger.error("lock_old_medical_records failed: %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Prescription expiry
# ---------------------------------------------------------------------------

@shared_task(
    name="core.expire_old_prescriptions",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def expire_old_prescriptions(self):
    """
    Mark pending prescriptions whose expiry_date has passed.
    Runs daily via Celery Beat.
    """
    try:
        from pharmacy.models import Prescription, PrescriptionStatus
        from datetime import date

        expired = Prescription.objects.filter(
            status=PrescriptionStatus.PENDING,
            expiry_date__lt=date.today(),
        )
        count = expired.count()
        expired.update(status=PrescriptionStatus.EXPIRED)

        logger.info("expire_old_prescriptions expired=%d", count)
        return {"expired": count}
    except Exception as exc:
        logger.error("expire_old_prescriptions failed: %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Drug expiry alerts
# ---------------------------------------------------------------------------

@shared_task(name="core.check_drug_expiry")
def check_drug_expiry(days_ahead=30):
    """
    Find drugs expiring within `days_ahead` days and log alerts.
    In production, this would send emails to the pharmacy manager.
    Runs weekly via Celery Beat.
    """
    from pharmacy.models import Drug
    drugs = Drug.objects.active().expiring_soon(days=days_ahead)
    results = []
    for drug in drugs:
        results.append({
            "id":          str(drug.pk),
            "name":        drug.name,
            "expiry_date": str(drug.expiry_date),
            "stock":       drug.stock_quantity,
        })
        logger.warning(
            "drug_expiry_alert drug=%s expiry=%s stock=%d",
            drug.name, drug.expiry_date, drug.stock_quantity,
        )
    return {"expiring_drugs": results}


# ---------------------------------------------------------------------------
# Low stock alerts
# ---------------------------------------------------------------------------

@shared_task(name="core.check_low_stock")
def check_low_stock():
    """Identify and alert on drugs at or below reorder level. Runs daily."""
    from pharmacy.models import Drug
    from django.db.models import F

    drugs = Drug.objects.active().filter(stock_quantity__lte=F("reorder_level"))
    results = []
    for drug in drugs:
        results.append({
            "id":            str(drug.pk),
            "name":          drug.name,
            "stock":         drug.stock_quantity,
            "reorder_level": drug.reorder_level,
        })
        logger.warning(
            "low_stock_alert drug=%s stock=%d reorder_level=%d",
            drug.name, drug.stock_quantity, drug.reorder_level,
        )
    return {"low_stock_drugs": results}


# ---------------------------------------------------------------------------
# Invoice overdue marking
# ---------------------------------------------------------------------------

@shared_task(name="core.mark_overdue_invoices")
def mark_overdue_invoices():
    """
    Find issued invoices past their due_at and mark them overdue.
    Runs daily at midnight via Celery Beat.
    """
    from billing.models import Invoice, InvoiceStatus

    now = timezone.now()
    overdue = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
        due_at__lt=now,
    )
    count = overdue.count()
    overdue.update(status=InvoiceStatus.OVERDUE)

    logger.info("mark_overdue_invoices updated=%d", count)
    return {"marked_overdue": count}


# ---------------------------------------------------------------------------
# Appointment reminders
# ---------------------------------------------------------------------------

@shared_task(name="core.send_appointment_reminders")
def send_appointment_reminders(hours_ahead=24):
    """
    Find booked appointments in the next `hours_ahead` hours that haven't
    had a reminder sent, and dispatch SMS/email reminders.
    Runs every 30 minutes via Celery Beat.
    """
    from appointments.models import Appointment, AppointmentStatus

    window_start = timezone.now()
    window_end   = timezone.now() + timedelta(hours=hours_ahead)

    pending = Appointment.objects.filter(
        status=AppointmentStatus.BOOKED,
        scheduled_at__gte=window_start,
        scheduled_at__lte=window_end,
        reminder_sent_at__isnull=True,
    ).select_related("patient", "doctor")

    sent = 0
    for appt in pending.iterator(chunk_size=50):
        try:
            # In production: dispatch to an SMS gateway (Africa's Talking, etc.)
            # and/or send email via the notification service.
            logger.info(
                "reminder_queued appointment=%s patient_mrn=%s scheduled=%s",
                appt.pk, appt.patient.mrn, appt.scheduled_at,
            )
            appt.reminder_sent_at = timezone.now()
            appt.save(update_fields=["reminder_sent_at"])
            sent += 1
        except Exception as exc:
            logger.error("reminder_failed appointment=%s error=%s", appt.pk, exc)

    logger.info("send_appointment_reminders sent=%d", sent)
    return {"reminders_sent": sent}


# ---------------------------------------------------------------------------
# Audit log archival (stub)
# ---------------------------------------------------------------------------

@shared_task(name="core.archive_audit_logs")
def archive_audit_logs():
    """
    Archive audit log partitions older than HMS_AUDIT_RETENTION_YEARS to S3.

    Production implementation:
    1. Identify the monthly partition table for (now - retention_years).
    2. COPY partition to CSV.
    3. Upload to s3://bucket/audit-archive/YYYY/MM/audit_YYYYMM.csv.gz
    4. DETACH the partition from the parent table.
    5. (Optional) DROP the detached partition after confirming S3 upload.

    This is a stub — the full implementation requires raw SQL and should
    be run as a DBA-reviewed migration, not a Celery task.
    """
    retention_years = getattr(settings, "HMS_AUDIT_RETENTION_YEARS", 7)
    cutoff = timezone.now() - timedelta(days=365 * retention_years)
    logger.info(
        "archive_audit_logs cutoff=%s retention_years=%d [STUB — not implemented]",
        cutoff.date(), retention_years,
    )
    return {"status": "stub", "cutoff": str(cutoff.date())}
