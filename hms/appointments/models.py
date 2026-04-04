"""
appointments/models.py
======================
Appointment scheduling with a strict status state machine and
database-level double-booking prevention.

State machine
-------------
booked → checked_in → in_progress → completed  (normal flow)
booked → cancelled                              (before arrival)
checked_in → no_show                            (patient absent)
All terminal states: completed, cancelled, no_show.

Double-booking prevention
-------------------------
UniqueConstraint with a partial condition covers the DB layer.
clean() covers the application layer (including duration overlap).
Both are required — the constraint catches concurrent requests;
clean() gives descriptive error messages to the API caller.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices and state machine
# ---------------------------------------------------------------------------

class AppointmentStatus(models.TextChoices):
    BOOKED      = "booked",      "Booked"
    CHECKED_IN  = "checked_in",  "Checked In"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED   = "completed",   "Completed"
    CANCELLED   = "cancelled",   "Cancelled"
    NO_SHOW     = "no_show",     "No Show"


class AppointmentType(models.TextChoices):
    CONSULTATION = "consultation", "Consultation"
    FOLLOW_UP    = "follow_up",    "Follow Up"
    PROCEDURE    = "procedure",    "Procedure"
    EMERGENCY    = "emergency",    "Emergency"
    TELEHEALTH   = "telehealth",   "Telehealth"


# Maps each status to the set of statuses it may legally transition to.
STATUS_TRANSITIONS = {
    AppointmentStatus.BOOKED:      frozenset({AppointmentStatus.CHECKED_IN,  AppointmentStatus.CANCELLED}),
    AppointmentStatus.CHECKED_IN:  frozenset({AppointmentStatus.IN_PROGRESS, AppointmentStatus.NO_SHOW}),
    AppointmentStatus.IN_PROGRESS: frozenset({AppointmentStatus.COMPLETED}),
    AppointmentStatus.COMPLETED:   frozenset(),
    AppointmentStatus.CANCELLED:   frozenset(),
    AppointmentStatus.NO_SHOW:     frozenset(),
}

TERMINAL_STATUSES = frozenset({
    AppointmentStatus.COMPLETED,
    AppointmentStatus.CANCELLED,
    AppointmentStatus.NO_SHOW,
})

ACTIVE_STATUSES = frozenset({
    AppointmentStatus.BOOKED,
    AppointmentStatus.CHECKED_IN,
    AppointmentStatus.IN_PROGRESS,
})


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class AppointmentManager(models.Manager):
    def active(self):
        return self.get_queryset().filter(status__in=ACTIVE_STATUSES)

    def today(self):
        today = timezone.localdate()
        return self.get_queryset().filter(scheduled_at__date=today)

    def upcoming(self):
        return self.active().filter(scheduled_at__gte=timezone.now())

    def for_patient(self, patient_id):
        return self.get_queryset().filter(patient_id=patient_id)

    def for_doctor(self, doctor_id):
        return self.get_queryset().filter(doctor_id=doctor_id)


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------

class Appointment(models.Model):
    """
    A scheduled encounter between one patient and one doctor.

    Relationships
    -------------
    → patients.Patient        : the attending patient.
    → doctors.Doctor          : the consulting doctor.
    → accounts.User (created_by): staff member who booked the slot.
    ← records.MedicalRecord   : clinical note from this encounter.
    ← billing.Invoice         : charges raised for this encounter.
    """

    DURATION_CHOICES = [
        (15,  "15 min"),
        (30,  "30 min"),
        (45,  "45 min"),
        (60,  "1 hour"),
        (90,  "1 h 30 min"),
        (120, "2 hours"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="appointments",
        db_index=True,
        help_text="PROTECT — cannot delete a patient who has appointments.",
    )
    doctor = models.ForeignKey(
        "doctors.Doctor",
        on_delete=models.PROTECT,
        related_name="appointments",
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="booked_appointments",
        help_text="Receptionist or admin who booked the slot.",
    )

    # ---- Scheduling -------------------------------------------------------
    scheduled_at     = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveSmallIntegerField(
        default=30,
        choices=DURATION_CHOICES,
    )

    # ---- Classification ---------------------------------------------------
    status = models.CharField(
        max_length=20,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.BOOKED,
        db_index=True,
    )
    appointment_type = models.CharField(
        max_length=20,
        choices=AppointmentType.choices,
        default=AppointmentType.CONSULTATION,
    )
    priority = models.PositiveSmallIntegerField(
        default=3,
        help_text="1=emergency, 2=urgent, 3=routine, 4=elective.",
    )

    # ---- Notes ------------------------------------------------------------
    chief_complaint     = models.TextField(
        blank=True,
        help_text="What the patient is coming for (entered at booking).",
    )
    notes               = models.TextField(blank=True, help_text="Receptionist/admin notes.")
    cancellation_reason = models.TextField(blank=True)

    # ---- Reminder tracking ------------------------------------------------
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    # ---- Timestamps -------------------------------------------------------
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AppointmentManager()

    class Meta:
        db_table            = "appointments_appointment"
        verbose_name        = "Appointment"
        verbose_name_plural = "Appointments"
        ordering            = ["-scheduled_at"]
        indexes = [
            models.Index(fields=["doctor", "scheduled_at"],   name="idx_appt_doctor_time"),
            models.Index(fields=["patient", "status"],        name="idx_appt_patient_status"),
            models.Index(fields=["scheduled_at", "status"],   name="idx_appt_time_status"),
            models.Index(fields=["status"],                   name="idx_appt_status"),
        ]
        constraints = [
            # DB-level: one active booking per doctor per exact start time.
            # Duration-overlap is caught by clean() — too complex for a simple unique constraint.
            models.UniqueConstraint(
                fields=["doctor", "scheduled_at"],
                condition=models.Q(status__in=["booked", "checked_in", "in_progress"]),
                name="unique_active_doctor_slot",
            ),
        ]

    def __str__(self):
        return (
            f"{self.patient} with {self.doctor} "
            f"@ {self.scheduled_at:%Y-%m-%d %H:%M} [{self.get_status_display()}]"
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def end_time(self):
        return self.scheduled_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_active(self):
        return self.status in ACTIVE_STATUSES

    @property
    def is_terminal(self):
        return self.status in TERMINAL_STATUSES

    @property
    def allowed_transitions(self):
        return list(STATUS_TRANSITIONS.get(self.status, frozenset()))

    @property
    def duration_display(self):
        h, m = divmod(self.duration_minutes, 60)
        if h and m:
            return f"{h}h {m}min"
        if h:
            return f"{h}h"
        return f"{m}min"

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def can_transition_to(self, new_status):
        return new_status in STATUS_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, new_status, actor=None):
        """
        The only correct way to change appointment status.
        Raises ValidationError on illegal transitions.

        Usage
        -----
        appointment.transition_to(AppointmentStatus.CHECKED_IN, actor=request.user)
        """
        if not self.can_transition_to(new_status):
            allowed = STATUS_TRANSITIONS.get(self.status, frozenset())
            raise ValidationError(
                f"Cannot transition '{self.status}' → '{new_status}'. "
                f"Allowed: {sorted(allowed) or 'none (terminal state)'}."
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        return self

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        errors = {}

        # 1. Future date check (only for new bookings)
        if self.scheduled_at and self.status == AppointmentStatus.BOOKED:
            if self.scheduled_at <= timezone.now():
                errors["scheduled_at"] = "Appointment must be scheduled in the future."

        # 2. Duration overlap check
        if self.scheduled_at and self.doctor_id:
            end = self.end_time
            overlapping = (
                Appointment.objects
                .filter(
                    doctor_id=self.doctor_id,
                    status__in=ACTIVE_STATUSES,
                    scheduled_at__lt=end,
                )
                .exclude(pk=self.pk)
            )
            for other in overlapping:
                if other.end_time > self.scheduled_at:
                    errors["scheduled_at"] = (
                        f"This slot overlaps with an existing appointment "
                        f"({other.scheduled_at:%H:%M}–{other.end_time:%H:%M})."
                    )
                    break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Skip full_clean during status-only updates to avoid
        # re-validating scheduled_at for past completed appointments.
        update_fields = kwargs.get("update_fields")
        if not update_fields or "scheduled_at" in update_fields:
            self.full_clean(exclude=["created_by", "patient", "doctor"])
        super().save(*args, **kwargs)
