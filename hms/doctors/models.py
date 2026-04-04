"""
doctors/models.py
=================
Doctor profile and weekly availability slots.

Design decisions:
  - Doctor is a 1:1 extension of accounts.User (role=doctor).
    Auth lives in User; clinical profile lives here.
  - First/last name denormalised from User — avoids a join on every
    appointment list query.
  - DoctorAvailability stores recurring weekly slots. Ad-hoc exceptions
    (holidays, sick leave) are handled by setting is_available=False on Doctor
    or by a future DoctorLeave model.
  - consultation_fee stored here so billing can pull it without a separate
    fee schedule table (which is a v2 concern).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class Department(models.TextChoices):
    GENERAL_MEDICINE = "general_medicine", "General Medicine"
    SURGERY          = "surgery",          "Surgery"
    PAEDIATRICS      = "paediatrics",      "Paediatrics"
    OBSTETRICS       = "obstetrics",       "Obstetrics & Gynaecology"
    CARDIOLOGY       = "cardiology",       "Cardiology"
    ORTHOPAEDICS     = "orthopaedics",     "Orthopaedics"
    DERMATOLOGY      = "dermatology",      "Dermatology"
    NEUROLOGY        = "neurology",        "Neurology"
    PSYCHIATRY       = "psychiatry",       "Psychiatry"
    RADIOLOGY        = "radiology",        "Radiology"
    LABORATORY       = "laboratory",       "Laboratory / Pathology"
    PHARMACY_DEPT    = "pharmacy",         "Pharmacy"
    EMERGENCY        = "emergency",        "Emergency"
    ICU              = "icu",              "Intensive Care Unit"
    DENTAL           = "dental",           "Dental"
    OPHTHALMOLOGY    = "ophthalmology",    "Ophthalmology"
    OTHER            = "other",            "Other"


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class DoctorManager(models.Manager):
    def available(self):
        return self.get_queryset().filter(is_available=True)

    def by_department(self, department):
        return self.get_queryset().filter(department=department, is_available=True)

    def by_specialisation(self, specialisation):
        return self.get_queryset().filter(
            specialisation__icontains=specialisation, is_available=True
        )


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class Doctor(models.Model):
    """
    Clinical profile for a user with role=doctor.

    Relationships
    -------------
    → accounts.User (OneToOne)       : authentication and role.
    ← appointments.Appointment       : all appointments for this doctor.
    ← records.MedicalRecord          : records authored by this doctor.
    ← pharmacy.Prescription          : prescriptions issued by this doctor.
    ← DoctorAvailability             : weekly time slots.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
        limit_choices_to={"role": "doctor"},
        help_text="Must be a User with role=doctor.",
    )

    # ---- Personal (denormalised for join-free listing) --------------------
    first_name = models.CharField(max_length=100)
    last_name  = models.CharField(max_length=100, db_index=True)
    phone      = models.CharField(max_length=30)
    photo_url  = models.URLField(blank=True, null=True)

    # ---- Professional credentials ----------------------------------------
    specialisation   = models.CharField(max_length=100, db_index=True)
    qualification    = models.CharField(
        max_length=255, blank=True,
        help_text="Degree(s) e.g. MBChB, MMED Surgery.",
    )
    licence_number   = models.CharField(
        max_length=60, unique=True,
        help_text="Medical council registration number.",
    )
    licence_expiry   = models.DateField(
        null=True, blank=True,
        help_text="Alert fires 60 days before expiry.",
    )
    department       = models.CharField(max_length=60, choices=Department.choices, db_index=True)
    years_experience = models.PositiveSmallIntegerField(default=0)
    bio              = models.TextField(blank=True)

    # ---- Scheduling -------------------------------------------------------
    consultation_fee     = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Base fee in the hospital's default currency.",
    )
    max_patients_per_day = models.PositiveSmallIntegerField(
        default=20,
        help_text="Appointment scheduler refuses bookings beyond this limit.",
    )
    is_available = models.BooleanField(
        default=True, db_index=True,
        help_text="False = on leave or unavailable; blocks new bookings.",
    )
    accepts_walk_in = models.BooleanField(default=False)

    # ---- Timestamps -------------------------------------------------------
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DoctorManager()

    class Meta:
        db_table            = "doctors_doctor"
        verbose_name        = "Doctor"
        verbose_name_plural = "Doctors"
        ordering            = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["department", "is_available"], name="idx_doctor_dept_avail"),
            models.Index(fields=["specialisation"],              name="idx_doctor_spec"),
            models.Index(fields=["licence_number"],              name="idx_doctor_licence"),
        ]

    def __str__(self):
        return f"Dr. {self.first_name} {self.last_name} — {self.specialisation}"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def full_name(self):
        return f"Dr. {self.first_name} {self.last_name}"

    @property
    def email(self):
        return self.user.email

    @property
    def licence_is_valid(self):
        from datetime import date
        if not self.licence_expiry:
            return True
        return self.licence_expiry >= date.today()

    @property
    def licence_expiring_soon(self):
        """True if licence expires within 60 days."""
        from datetime import date, timedelta
        if not self.licence_expiry:
            return False
        return self.licence_expiry <= date.today() + timedelta(days=60)

    # ------------------------------------------------------------------
    # Business methods
    # ------------------------------------------------------------------

    def todays_appointment_count(self):
        from django.utils import timezone
        today = timezone.localdate()
        return self.appointments.filter(
            scheduled_at__date=today,
            status__in=["booked", "checked_in", "in_progress"],
        ).count()

    def is_fully_booked_today(self):
        return self.todays_appointment_count() >= self.max_patients_per_day

    def get_appointments_on(self, target_date):
        return self.appointments.filter(
            scheduled_at__date=target_date,
        ).order_by("scheduled_at")


# ---------------------------------------------------------------------------
# DoctorAvailability
# ---------------------------------------------------------------------------

class DoctorAvailability(models.Model):
    """
    Recurring weekly availability slot for a doctor.

    One doctor may have multiple slots per day (e.g. 08:00–12:00 and 14:00–17:00).
    The appointment scheduler checks these before allowing a booking.
    """

    WEEKDAYS = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doctor     = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name="availability",
    )
    weekday    = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time   = models.TimeField()
    is_active  = models.BooleanField(default=True)

    class Meta:
        db_table        = "doctors_availability"
        unique_together = ("doctor", "weekday", "start_time")
        ordering        = ["weekday", "start_time"]

    def __str__(self):
        return (
            f"{self.doctor.full_name} — "
            f"{self.get_weekday_display()} "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        )

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be after start time."})
