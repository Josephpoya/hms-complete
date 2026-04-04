"""
core/apps.py
============
Registers the core app and connects audit signals.
"""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name  = "core"
    label = "core"

    def ready(self):
        # Register signal-based audit handlers for tracked models
        from core.audit import AuditSignalHandler
        AuditSignalHandler.register()

        # Register Celery Beat schedule (idempotent)
        self._register_celery_beat_schedule()

    def _register_celery_beat_schedule(self):
        """
        Register periodic task schedule in the database via django-celery-beat.
        Called on startup — uses update_or_create so it is safe to run repeatedly.
        """
        try:
            from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
            import json

            # Every hour: lock old medical records
            hourly, _ = IntervalSchedule.objects.get_or_create(
                every=1, period=IntervalSchedule.HOURS
            )
            PeriodicTask.objects.update_or_create(
                name="Lock old medical records",
                defaults={
                    "task":     "core.lock_old_medical_records",
                    "interval": hourly,
                    "enabled":  True,
                },
            )

            # Daily at 01:00 UTC
            daily_1am, _ = CrontabSchedule.objects.get_or_create(
                minute="0", hour="1", day_of_week="*",
                day_of_month="*", month_of_year="*",
            )
            for task_name, task_path in [
                ("Expire old prescriptions",   "core.expire_old_prescriptions"),
                ("Mark overdue invoices",       "core.mark_overdue_invoices"),
                ("Check low drug stock",        "core.check_low_stock"),
            ]:
                PeriodicTask.objects.update_or_create(
                    name=task_name,
                    defaults={"task": task_path, "crontab": daily_1am, "enabled": True},
                )

            # Weekly on Monday 02:00 UTC
            weekly, _ = CrontabSchedule.objects.get_or_create(
                minute="0", hour="2", day_of_week="1",
                day_of_month="*", month_of_year="*",
            )
            PeriodicTask.objects.update_or_create(
                name="Check drug expiry",
                defaults={
                    "task":     "core.check_drug_expiry",
                    "crontab":  weekly,
                    "enabled":  True,
                    "kwargs":   json.dumps({"days_ahead": 30}),
                },
            )

            # Every 30 min: appointment reminders
            every_30, _ = IntervalSchedule.objects.get_or_create(
                every=30, period=IntervalSchedule.MINUTES
            )
            PeriodicTask.objects.update_or_create(
                name="Send appointment reminders",
                defaults={
                    "task":     "core.send_appointment_reminders",
                    "interval": every_30,
                    "enabled":  True,
                },
            )

        except Exception:
            # Silently skip if DB tables don't exist yet (first migration)
            pass
