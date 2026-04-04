"""
patients/models.py
==================
Patient demographics and identity.

Design decisions:
  - MRN generated via PostgreSQL sequence — collision-safe under concurrency.
  - Soft-delete only: patient records must be retained for medical-legal reasons.
  - national_id: unique but nullable (not all patients carry ID); encrypt in prod.
  - allergies / chronic_conditions: free text for now; v2 will normalise these
    into a separate table (patients_allergy, patients_condition) with ICD codes.
  - Emergency contact stored inline — simple enough to not warrant a separate table.
  - Insurance stored inline; complex multi-payer scenarios handled by billing layer.
"""

import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class Gender(models.TextChoices):
    MALE           = "male",             "Male"
    FEMALE         = "female",           "Female"
    OTHER          = "other",            "Other"
    PREFER_NOT     = "prefer_not_to_say","Prefer not to say"


class BloodType(models.TextChoices):
    A_POS  = "A+",  "A+"
    A_NEG  = "A-",  "A-"
    B_POS  = "B+",  "B+"
    B_NEG  = "B-",  "B-"
    AB_POS = "AB+", "AB+"
    AB_NEG = "AB-", "AB-"
    O_POS  = "O+",  "O+"
    O_NEG  = "O-",  "O-"


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class PatientManager(models.Manager):
    def active(self):
        return self.get_queryset().filter(is_active=True)

    def search(self, query):
        """Quick name / MRN / phone lookup for receptionist search bar."""
        from django.db.models import Q
        return self.active().filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(mrn__icontains=query)
            | Q(phone__icontains=query)
        )


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------

class Patient(models.Model):
    """
    Core patient record — demographics, contact, clinical flags.

    Relationships
    -------------
    → accounts.User  (created_by)   : staff member who registered the patient.
    ← appointments.Appointment      : all visits for this patient.
    ← records.MedicalRecord         : full EHR history.
    ← billing.Invoice               : billing history.
    ← pharmacy.Prescription         : prescription history.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    mrn = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        editable=False,
        help_text="Auto-generated Medical Record Number (MRN-0000001).",
    )

    # ---- Core demographics ------------------------------------------------
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100, db_index=True)
    date_of_birth = models.DateField()
    gender        = models.CharField(max_length=20, choices=Gender.choices)
    blood_type    = models.CharField(
        max_length=5, choices=BloodType.choices,
        blank=True, null=True,
    )
    nationality = models.CharField(max_length=80, blank=True, null=True)

    # ---- Contact ----------------------------------------------------------
    phone   = models.CharField(max_length=30, help_text="E.164 format preferred: +256700000000")
    email   = models.EmailField(max_length=255, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    # ---- Identity (encrypt at rest in production) -------------------------
    national_id = models.CharField(
        max_length=50, unique=True, blank=True, null=True,
        help_text="National ID / Passport number. Encrypted at rest.",
    )

    # ---- Clinical flags ---------------------------------------------------
    allergies = models.TextField(
        blank=True, null=True,
        help_text="Comma-separated allergens. Will be normalised in v2.",
    )
    chronic_conditions = models.TextField(
        blank=True, null=True,
        help_text="Pre-existing conditions. Will be normalised in v2.",
    )
    is_diabetic       = models.BooleanField(default=False)
    is_hypertensive   = models.BooleanField(default=False)
    is_hiv_positive   = models.BooleanField(
        default=False,
        help_text="Sensitive field — access restricted to clinical staff.",
    )

    # ---- Emergency contact ------------------------------------------------
    emergency_contact_name     = models.CharField(max_length=200, blank=True, null=True)
    emergency_contact_phone    = models.CharField(max_length=30,  blank=True, null=True)
    emergency_contact_relation = models.CharField(max_length=60,  blank=True, null=True)

    # ---- Insurance --------------------------------------------------------
    insurance_provider = models.CharField(max_length=150, blank=True, null=True)
    insurance_number   = models.CharField(max_length=80,  blank=True, null=True)
    insurance_expiry   = models.DateField(blank=True, null=True)

    # ---- Audit ------------------------------------------------------------
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="registered_patients",
        help_text="Staff member who registered this patient.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    is_active  = models.BooleanField(
        default=True, db_index=True,
        help_text="False = soft-deleted. Never hard-delete patient records.",
    )

    objects = PatientManager()

    class Meta:
        db_table            = "patients_patient"
        verbose_name        = "Patient"
        verbose_name_plural = "Patients"
        ordering            = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["last_name", "first_name"], name="idx_patient_name"),
            models.Index(fields=["mrn"],                     name="idx_patient_mrn"),
            models.Index(fields=["phone"],                   name="idx_patient_phone"),
            models.Index(fields=["is_active"],               name="idx_patient_active"),
            models.Index(fields=["created_at"],              name="idx_patient_created"),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.mrn})"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        today = date.today()
        dob   = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def has_allergies(self):
        return bool(self.allergies and self.allergies.strip())

    @property
    def insurance_is_valid(self):
        if not self.insurance_expiry:
            return False
        return self.insurance_expiry >= date.today()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        if self.date_of_birth and self.date_of_birth >= date.today():
            raise ValidationError({"date_of_birth": "Date of birth must be in the past."})

    # ------------------------------------------------------------------
    # Save / MRN generation
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if not self.mrn:
            self.mrn = self._generate_mrn()
        self.full_clean(exclude=["created_by"])
        super().save(*args, **kwargs)

    @classmethod
    def _generate_mrn(cls):
        prefix = getattr(settings, "HMS_MRN_PREFIX", "MRN")
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval('patients_mrn_seq')")
            seq = cursor.fetchone()[0]
        return f"{prefix}-{seq:07d}"

    # ------------------------------------------------------------------
    # Business methods
    # ------------------------------------------------------------------

    def soft_delete(self):
        """Mark as inactive — never call delete() directly."""
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def get_latest_record(self):
        return self.medical_records.order_by("-recorded_at").first()

    def get_active_prescriptions(self):
        return self.prescriptions.filter(status="pending")

    def get_outstanding_balance(self):
        from decimal import Decimal
        return (
            self.invoices
            .filter(status__in=["issued", "partially_paid", "overdue"])
            .aggregate(total=models.Sum("total_amount"))["total"]
            or Decimal("0.00")
        )
