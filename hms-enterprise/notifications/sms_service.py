"""
notifications/sms_service.py
=============================
Enterprise SMS notification service using Africa's Talking.

Why Africa's Talking?
---------------------
Africa's Talking (africastalking.com) is the dominant SMS provider across
East and Central Africa (Uganda, Kenya, Tanzania, Rwanda). It supports:
  - Shortcodes and long numbers
  - Delivery receipts via webhook
  - Bulk messaging at volume discounts
  - Local regulatory compliance (UCC, CA, TCRA)

Alternative providers are abstracted behind SMSProvider so you can swap
them without touching business logic.

Usage
-----
  from notifications.sms_service import sms_service, SMSTemplate

  # Send immediately (synchronous — use in Celery tasks only)
  result = sms_service.send(
      to      = "+256700000000",
      message = SMSTemplate.appointment_reminder(appt),
  )

  # Queue for async delivery (recommended in views)
  from notifications.tasks import send_sms_task
  send_sms_task.delay(to="+256700000000", message=SMSTemplate.appointment_reminder(appt))
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from django.conf import settings

logger = logging.getLogger("hms.notifications")


# ─── Result type ──────────────────────────────────────────────────────────────
@dataclass
class SMSResult:
    success:    bool
    provider:   str
    message_id: Optional[str] = None
    recipient:  Optional[str] = None
    status:     Optional[str] = None
    cost:       Optional[str] = None
    error:      Optional[str] = None


# ─── Abstract provider ────────────────────────────────────────────────────────
class SMSProvider(ABC):
    @abstractmethod
    def send(self, to: str, message: str, sender_id: Optional[str] = None) -> SMSResult:
        """Send a single SMS. Returns SMSResult."""
        ...

    @abstractmethod
    def send_bulk(self, recipients: list[dict], message: str) -> list[SMSResult]:
        """Send same message to multiple recipients efficiently."""
        ...


# ─── Africa's Talking provider ────────────────────────────────────────────────
class AfricasTalkingProvider(SMSProvider):
    """
    Africa's Talking SMS gateway.

    Setup:
    1. Sign up at https://account.africastalking.com
    2. Create a new app and note the API Key
    3. Register a sender ID (shortcode or alphanumeric — subject to carrier approval)
    4. Set in .env:
         AT_API_KEY=your-api-key
         AT_USERNAME=your-sandbox-or-production-username
         AT_SENDER_ID=HMS           (or your registered shortcode)
         AT_ENVIRONMENT=production  (or sandbox for testing)

    Sandbox:
      Set AT_ENVIRONMENT=sandbox and AT_USERNAME=sandbox to test without
      sending real SMS. Responses look identical to production.
    """

    def __init__(self):
        import africastalking
        environment = getattr(settings, "AT_ENVIRONMENT", "sandbox")
        username    = getattr(settings, "AT_USERNAME",    "sandbox")
        api_key     = getattr(settings, "AT_API_KEY",     "")

        africastalking.initialize(username, api_key)
        self._sms = africastalking.SMS
        self._sender = getattr(settings, "AT_SENDER_ID", None)
        logger.info("Africa's Talking SMS provider initialised (environment=%s)", environment)

    def send(self, to: str, message: str, sender_id: Optional[str] = None) -> SMSResult:
        """
        Send a single SMS via Africa's Talking.

        to      : E.164 format (+256700000000).
        message : Max 160 chars for a single SMS segment.
                  Longer messages are sent as concatenated SMS (billed per segment).
        """
        to = self._normalize_phone(to)
        sender = sender_id or self._sender

        try:
            response = self._sms.send(
                message   = message,
                recipients = [to],
                sender_id  = sender,
            )
            recipient_data = response.get("SMSMessageData", {}).get("Recipients", [{}])[0]
            status = recipient_data.get("status", "Unknown")
            success = status in ("Success", "Sent")

            result = SMSResult(
                success    = success,
                provider   = "africastalking",
                message_id = recipient_data.get("messageId"),
                recipient  = to,
                status     = status,
                cost       = recipient_data.get("cost"),
                error      = None if success else recipient_data.get("statusCode"),
            )

            if success:
                logger.info("SMS sent: to=%s messageId=%s cost=%s", to, result.message_id, result.cost)
            else:
                logger.warning("SMS failed: to=%s status=%s error=%s", to, status, result.error)

            return result

        except Exception as exc:
            logger.error("SMS exception: to=%s error=%s", to, exc, exc_info=True)
            return SMSResult(success=False, provider="africastalking", recipient=to, error=str(exc))

    def send_bulk(self, recipients: list[dict], message: str) -> list[SMSResult]:
        """
        Send the same message to many recipients in one API call.
        Each dict in recipients must have a 'phone' key.
        """
        phones = [self._normalize_phone(r["phone"]) for r in recipients]
        try:
            response = self._sms.send(
                message    = message,
                recipients = phones,
                sender_id  = self._sender,
            )
            results = []
            for rd in response.get("SMSMessageData", {}).get("Recipients", []):
                status = rd.get("status", "Unknown")
                results.append(SMSResult(
                    success    = status in ("Success", "Sent"),
                    provider   = "africastalking",
                    message_id = rd.get("messageId"),
                    recipient  = rd.get("number"),
                    status     = status,
                    cost       = rd.get("cost"),
                ))
            logger.info("Bulk SMS sent: count=%d", len(results))
            return results
        except Exception as exc:
            logger.error("Bulk SMS exception: %s", exc, exc_info=True)
            return [SMSResult(success=False, provider="africastalking", error=str(exc))
                    for _ in recipients]

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """
        Normalise a phone number to E.164.
        Uganda: 07XXXXXXXX → +2567XXXXXXXX
        Kenya:  07XXXXXXXX → +2547XXXXXXXX
        """
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith("0") and len(phone) >= 10:
            phone = "+256" + phone[1:]   # Default to Uganda — extend per hospital location
        if not phone.startswith("+"):
            phone = "+" + phone
        return phone


# ─── Console provider (development / testing) ─────────────────────────────────
class ConsoleSMSProvider(SMSProvider):
    """Prints SMS to stdout instead of sending. Use in development."""

    def send(self, to: str, message: str, sender_id: Optional[str] = None) -> SMSResult:
        print(f"\n[SMS → {to}]\n{message}\n")
        return SMSResult(
            success=True, provider="console",
            message_id="console-test", recipient=to, status="Sent",
        )

    def send_bulk(self, recipients: list[dict], message: str) -> list[SMSResult]:
        results = []
        for r in recipients:
            results.append(self.send(r.get("phone", "unknown"), message))
        return results


# ─── SMS Service (singleton facade) ───────────────────────────────────────────
class SMSService:
    """
    Singleton SMS service. Selects the correct provider based on settings.
    Handles delivery logging to the database.

    Use this class, not the providers directly.
    """
    _instance: Optional["SMSService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_provider()
        return cls._instance

    def _init_provider(self):
        provider_name = getattr(settings, "SMS_PROVIDER", "console")
        if provider_name == "africastalking":
            self._provider: SMSProvider = AfricasTalkingProvider()
        else:
            self._provider = ConsoleSMSProvider()
            logger.info("Using console SMS provider (no real SMS will be sent)")

    def send(self, to: str, message: str, appointment_id: Optional[str] = None) -> SMSResult:
        result = self._provider.send(to, message)
        self._log(result, message, appointment_id)
        return result

    def send_bulk(self, recipients: list[dict], message: str) -> list[SMSResult]:
        results = self._provider.send_bulk(recipients, message)
        for r in results:
            self._log(r, message)
        return results

    def _log(self, result: SMSResult, message: str, appointment_id: Optional[str] = None) -> None:
        """Write delivery record to database (async in Celery context)."""
        try:
            from notifications.models import SMSLog
            SMSLog.objects.create(
                recipient     = result.recipient or "",
                message       = message[:500],
                provider      = result.provider,
                message_id    = result.message_id or "",
                status        = result.status or ("sent" if result.success else "failed"),
                cost          = result.cost or "",
                error         = result.error or "",
                appointment_id = appointment_id,
            )
        except Exception as exc:
            logger.warning("SMSLog write failed: %s", exc)


# Singleton instance
sms_service = SMSService()


# ─── Message templates ────────────────────────────────────────────────────────
class SMSTemplate:
    """
    All SMS message templates in one place.
    Keep messages under 160 chars for a single SMS segment.
    """

    @staticmethod
    def appointment_reminder(appointment) -> str:
        """
        Reminder sent 24h and 2h before the appointment.
        ~145 characters.
        """
        from django.utils import timezone
        from django.utils.formats import date_format
        import pytz

        local_tz  = pytz.timezone(settings.TIME_ZONE)
        appt_time = appointment.scheduled_at.astimezone(local_tz)
        date_str  = appt_time.strftime("%-d %b")
        time_str  = appt_time.strftime("%I:%M %p")

        return (
            f"HMS Reminder: Appt with {appointment.doctor.full_name} "
            f"on {date_str} at {time_str}. "
            f"Ref: {appointment.patient.mrn}. "
            f"Call 0800-HMS-001 to reschedule."
        )

    @staticmethod
    def appointment_confirmation(appointment) -> str:
        """Sent immediately after booking."""
        from django.utils import timezone
        import pytz
        local_tz  = pytz.timezone(settings.TIME_ZONE)
        appt_time = appointment.scheduled_at.astimezone(local_tz)
        return (
            f"HMS: Appointment confirmed. "
            f"{appointment.doctor.full_name} on {appt_time.strftime('%-d %b at %I:%M %p')}. "
            f"Bring this ref: {appointment.patient.mrn}."
        )

    @staticmethod
    def appointment_cancelled(appointment) -> str:
        """Sent when appointment is cancelled."""
        return (
            f"HMS: Your appointment with {appointment.doctor.full_name} "
            f"has been cancelled. Contact us at 0800-HMS-001 to rebook."
        )

    @staticmethod
    def prescription_ready(prescription) -> str:
        """Sent when a prescription is dispensed."""
        return (
            f"HMS: Your prescription for {prescription.drug.name} "
            f"({prescription.dosage}, {prescription.frequency}) "
            f"is ready for collection. Ref: {prescription.patient.mrn}."
        )

    @staticmethod
    def invoice_issued(invoice) -> str:
        """Sent when an invoice is issued."""
        return (
            f"HMS Invoice {invoice.invoice_number}: "
            f"{invoice.currency} {float(invoice.total_amount):,.0f} due by "
            f"{invoice.due_at.strftime('%-d %b %Y') if invoice.due_at else 'TBC'}. "
            f"Pay via mobile money or at the cashier."
        )

    @staticmethod
    def low_stock_alert(drug) -> str:
        """Internal alert to pharmacy manager (not sent to patients)."""
        return (
            f"HMS STOCK ALERT: {drug.name} ({drug.generic_name}) "
            f"stock at {drug.stock_quantity} {drug.unit}s "
            f"(reorder level: {drug.reorder_level}). Please reorder."
        )
