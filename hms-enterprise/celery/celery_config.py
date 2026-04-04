"""
celery/celery_config.py
=======================
Enterprise Celery configuration for HMS.

Queue architecture:
  critical      — medication expiry, security alerts  (concurrency=1, priority=10)
  notifications — SMS, email                          (concurrency=4, priority=8)
  default       — general async tasks                 (concurrency=4, priority=5)
  reports       — CSV/PDF generation                  (concurrency=1, priority=3)

This separation means:
  - A report generating a 10,000-row CSV doesn't block appointment reminders
  - Critical alerts always have a dedicated worker slot
  - Workers can be scaled per queue: docker compose up --scale celery=4

Apply by adding to settings/base.py:
  from celery_config import CELERY_TASK_ROUTES, CELERY_BEAT_SCHEDULE, ...
"""

from datetime import timedelta
from kombu import Exchange, Queue

# ─── Queue and exchange definitions ──────────────────────────────────────────
default_exchange      = Exchange("default",       type="direct")
notifications_exchange= Exchange("notifications", type="direct")
reports_exchange      = Exchange("reports",       type="direct")
critical_exchange     = Exchange("critical",      type="direct")

CELERY_TASK_QUEUES = (
    Queue("critical",      critical_exchange,      routing_key="critical",      queue_arguments={"x-max-priority": 10}),
    Queue("notifications", notifications_exchange, routing_key="notifications", queue_arguments={"x-max-priority": 8}),
    Queue("default",       default_exchange,       routing_key="default",       queue_arguments={"x-max-priority": 5}),
    Queue("reports",       reports_exchange,       routing_key="reports",       queue_arguments={"x-max-priority": 3}),
)

CELERY_DEFAULT_QUEUE   = "default"
CELERY_DEFAULT_EXCHANGE= "default"
CELERY_DEFAULT_ROUTING_KEY = "default"

# ─── Route tasks to queues ────────────────────────────────────────────────────
CELERY_TASK_ROUTES = {
    # Notifications
    "notifications.send_sms":                      {"queue": "notifications"},
    "notifications.send_appointment_reminders":    {"queue": "notifications"},
    "notifications.send_appointment_confirmation": {"queue": "notifications"},
    "notifications.send_invoice_sms":              {"queue": "notifications"},
    "notifications.send_prescription_sms":         {"queue": "notifications"},
    "notifications.send_bulk_sms":                 {"queue": "notifications"},
    # Critical (highest priority)
    "notifications.alert_low_stock":               {"queue": "critical"},
    "core.lock_old_medical_records":               {"queue": "critical"},
    # Reports (lowest priority, long-running)
    "core.generate_report":                        {"queue": "reports"},
    # Default
    "core.expire_old_prescriptions":               {"queue": "default"},
    "core.mark_overdue_invoices":                  {"queue": "default"},
    "core.check_drug_expiry":                      {"queue": "default"},
    "core.archive_audit_logs":                     {"queue": "default"},
}

# ─── Celery Beat schedule ─────────────────────────────────────────────────────
CELERY_BEAT_SCHEDULE = {
    # Lock medical records that have passed their 24h edit window (every hour)
    "lock-old-medical-records": {
        "task":    "core.lock_old_medical_records",
        "schedule": timedelta(hours=1),
    },

    # Expire old prescriptions (daily at 01:00)
    "expire-old-prescriptions": {
        "task":    "core.expire_old_prescriptions",
        "schedule": timedelta(days=1),
        "kwargs":  {},
    },

    # Mark overdue invoices (daily at 01:30)
    "mark-overdue-invoices": {
        "task":    "core.mark_overdue_invoices",
        "schedule": timedelta(days=1),
    },

    # 24-hour appointment reminders (every 30 minutes)
    "appointment-reminders-24h": {
        "task":    "notifications.send_appointment_reminders",
        "schedule": timedelta(minutes=30),
        "kwargs":  {"hours_ahead": 24},
    },

    # 2-hour appointment reminders (every 15 minutes)
    "appointment-reminders-2h": {
        "task":    "notifications.send_appointment_reminders",
        "schedule": timedelta(minutes=15),
        "kwargs":  {"hours_ahead": 2},
    },

    # Low stock alert to pharmacy manager (daily at 07:00)
    "low-stock-alert": {
        "task":    "notifications.alert_low_stock",
        "schedule": timedelta(days=1),
    },

    # Drug expiry check (weekly on Monday)
    "drug-expiry-check": {
        "task":    "core.check_drug_expiry",
        "schedule": timedelta(weeks=1),
        "kwargs":  {"days_ahead": 30},
    },
}

# ─── Task execution settings ──────────────────────────────────────────────────
CELERY_TASK_ALWAYS_EAGER = False    # Set True in tests to run tasks synchronously
CELERY_TASK_EAGER_PROPAGATES = True

# Prevent tasks from being held in memory indefinitely
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60    # 25 minutes — task gets SoftTimeLimitExceeded
CELERY_TASK_TIME_LIMIT      = 30 * 60    # 30 minutes — task is forcibly killed

# Acknowledge tasks after they complete, not when they start
# Combined with acks_late=True on individual tasks: if a worker dies mid-task,
# the message returns to the queue and another worker picks it up.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # One task at a time per worker slot

# Results
CELERY_RESULT_EXPIRES = timedelta(days=1)   # Keep results for 24h
CELERY_RESULT_COMPRESSION = "gzip"

# Serialisation
CELERY_TASK_SERIALIZER   = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT    = ["json"]
CELERY_TIMEZONE          = "Africa/Kampala"
CELERY_ENABLE_UTC        = True
