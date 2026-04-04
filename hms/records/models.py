"""
records/models.py
=================
Electronic Health Records (EHR) in SOAP format.

Design decisions:
  - SOAP structure (Subjective / Objective / Assessment / Plan) is the
    clinical standard; all four sections are nullable to allow mid-consultation
    saves without forcing the doctor to complete all fields in one sitting.
  - is_locked: set True 24 hours after creation by a Celery task.
    After locking, the record is immutable — save() raises ValidationError.
    This satisfies medical-legal requirements (no backdating).
  - ICD-10 code stored as a plain CharField — full ICD-10 lookup table would
    be a separate fixtures/data migration in production.
  - vitals stored as JSONB — schema varies by ward (ICU has different fields
    than a general consultation). Keys are validated by the serializer.
  - attachments stored as a JSONB array of S3 references — no binary data
    in PostgreSQL.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class MedicalRecordManager(models.Manager):
    def for_patient(self, patient_id):
        return self.get_queryset().filter(patient_id=patient_id).order_by("-recorded_at")

    def unlocked(self):
        return self.get_queryset().filter(is_locked=False)

    def by_icd10(self, code):
        return self.get_queryset().filter(icd10_code__iexact=code)


# ---------------------------------------------------------------------------
# MedicalRecord
# ---------------------------------------------------------------------------

class MedicalRecord(models.Model):
    """
    One clinical encounter note, authored by a doctor.

    SOAP structure
    --------------
    Subjective  — what the patient reports (chief complaint, history).
    Objective   — what the clinician observes (physical exam, measurements).
    Assessment  — clinical reasoning and diagnosis.
    Plan        — treatment decisions: meds, investigations, referrals, follow-up.

    Immutability
    ------------
    Records are editable only by the authoring doctor, and only within
    24 hours of creation. After that, is_locked=True is set by Celery and
    save() raises ValidationError. Amendments must be documented as
    addendum notes (future v2 feature) rather than modifying the original.

    Relationships
    -------------
    → patients.Patient              : the patient this record belongs to.
    → doctors.Doctor                : the doctor who authored the note.
    → appointments.Appointment      : the encounter that prompted this record.
    ← pharmacy.Prescription         : prescriptions linked to this note.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="medical_records",
        db_index=True,
        help_text="PROTECT — records must outlive patient soft-deletion.",
    )
    doctor = models.ForeignKey(
        "doctors.Doctor",
        on_delete=models.SET_NULL,
        null=True,
        related_name="medical_records",
        db_index=True,
        help_text="SET NULL — record survives if a doctor leaves the system.",
    )
    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_record",
        help_text="The encounter this record documents. May be null for legacy imports.",
    )

    # ---- SOAP Notes -------------------------------------------------------
    subjective = models.TextField(
        blank=True, null=True,
        help_text="Patient-reported: chief complaint, symptom history, pain scale.",
    )
    objective = models.TextField(
        blank=True, null=True,
        help_text="Clinician findings: physical exam, observations.",
    )
    assessment = models.TextField(
        blank=True, null=True,
        help_text="Diagnosis and clinical reasoning.",
    )
    plan = models.TextField(
        blank=True, null=True,
        help_text="Treatment plan: medications, investigations, referrals, follow-up date.",
    )

    # ---- Diagnosis coding -------------------------------------------------
    icd10_code = models.CharField(
        max_length=10, blank=True, null=True, db_index=True,
        help_text="Primary ICD-10 diagnosis code e.g. J06.9 (URTI).",
    )
    icd10_description = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Human-readable label pulled from ICD-10 lookup at save time.",
    )
    secondary_diagnoses = models.JSONField(
        null=True, blank=True,
        help_text="Array of {code, description} for co-morbidities.",
    )

    # ---- Vitals (JSONB) ---------------------------------------------------
    # Allowed keys (validated by serializer):
    #   bp_systolic, bp_diastolic, pulse, temperature,
    #   spo2, respiratory_rate, weight_kg, height_cm, bmi,
    #   blood_glucose, urine_output
    vitals = models.JSONField(
        null=True, blank=True,
        help_text="Structured vitals. Schema varies by ward — serializer validates keys.",
    )

    # ---- Attachments (JSONB array of S3 references) ----------------------
    # Each element: {key, filename, content_type, size, uploaded_at}
    attachments = models.JSONField(
        null=True, blank=True,
        help_text="Array of S3 file references. No binary data stored in DB.",
    )

    # ---- Follow-up --------------------------------------------------------
    follow_up_date = models.DateField(
        null=True, blank=True,
        help_text="Date the doctor wants to see the patient again.",
    )
    referral_to    = models.CharField(
        max_length=200, blank=True,
        help_text="Department or specialist the patient is referred to.",
    )
    referral_notes = models.TextField(blank=True)

    # ---- Immutability lock ------------------------------------------------
    is_locked = models.BooleanField(
        default=False,
        help_text="Set True 24h after creation by Celery. Prevents any further edits.",
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    # ---- Timestamps -------------------------------------------------------
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at  = models.DateTimeField(auto_now=True)

    objects = MedicalRecordManager()

    class Meta:
        db_table            = "records_medicalrecord"
        verbose_name        = "Medical Record"
        verbose_name_plural = "Medical Records"
        ordering            = ["-recorded_at"]
        indexes = [
            models.Index(fields=["patient", "recorded_at"],  name="idx_record_patient_ts"),
            models.Index(fields=["doctor",  "recorded_at"],  name="idx_record_doctor_ts"),
            models.Index(fields=["icd10_code"],              name="idx_record_icd10"),
            models.Index(fields=["is_locked"],               name="idx_record_locked"),
        ]

    def __str__(self):
        return (
            f"Record [{self.icd10_code or 'no code'}] "
            f"for {self.patient} "
            f"by {self.doctor} "
            f"on {self.recorded_at:%Y-%m-%d}"
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_complete(self):
        """All four SOAP sections are filled."""
        return all([self.subjective, self.objective, self.assessment, self.plan])

    @property
    def has_attachments(self):
        return bool(self.attachments)

    @property
    def attachment_count(self):
        return len(self.attachments) if self.attachments else 0

    @property
    def hours_since_creation(self):
        delta = timezone.now() - self.recorded_at
        return delta.total_seconds() / 3600

    @property
    def is_within_edit_window(self):
        """Editable within the first 24 hours."""
        return self.hours_since_creation < 24 and not self.is_locked

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def lock(self):
        """
        Permanently lock this record.
        Called by the Celery `lock_old_medical_records` periodic task.
        Bypasses the locked check in save() by calling super().save() directly.
        """
        if not self.is_locked:
            self.is_locked = True
            self.locked_at = timezone.now()
            super(MedicalRecord, self).save(update_fields=["is_locked", "locked_at"])

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        # Block edits on locked records (except the lock() method itself
        # which calls super().save() and never passes through here).
        if self.pk and self.is_locked:
            raise ValidationError(
                "This medical record has been locked and cannot be modified. "
                "Records are locked 24 hours after creation. "
                "Contact the administrator if an amendment is required."
            )
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Attachment management
    # ------------------------------------------------------------------

    def add_attachment(self, key, filename, content_type, size_bytes):
        """
        Register an S3 file reference on this record.
        Called after a successful S3 upload from RecordAttachmentView.
        """
        if self.is_locked:
            raise ValidationError("Cannot add attachments to a locked record.")
        attachments = list(self.attachments or [])
        attachments.append({
            "key":          key,
            "filename":     filename,
            "content_type": content_type,
            "size":         size_bytes,
            "uploaded_at":  timezone.now().isoformat(),
        })
        self.attachments = attachments
        self.save(update_fields=["attachments", "updated_at"])

    def remove_attachment(self, key):
        """Remove an S3 reference by key (does not delete from S3 — do that separately)."""
        if self.is_locked:
            raise ValidationError("Cannot remove attachments from a locked record.")
        if not self.attachments:
            raise ValueError("No attachments on this record.")
        original_count = len(self.attachments)
        self.attachments = [a for a in self.attachments if a.get("key") != key]
        if len(self.attachments) == original_count:
            raise ValueError(f"Attachment with key '{key}' not found.")
        self.save(update_fields=["attachments", "updated_at"])

    # ------------------------------------------------------------------
    # Vitals helpers
    # ------------------------------------------------------------------

    VITAL_KEYS = frozenset({
        "bp_systolic", "bp_diastolic", "pulse", "temperature",
        "spo2", "respiratory_rate", "weight_kg", "height_cm",
        "bmi", "blood_glucose", "urine_output",
    })

    def set_vitals(self, **kwargs):
        """
        Merge new vitals values into the existing JSONB.
        Unknown keys raise ValueError.
        """
        if self.is_locked:
            raise ValidationError("Cannot update vitals on a locked record.")
        unknown = set(kwargs) - self.VITAL_KEYS
        if unknown:
            raise ValueError(f"Unknown vital signs: {unknown}. Allowed: {self.VITAL_KEYS}")
        vitals = dict(self.vitals or {})
        vitals.update(kwargs)
        self.vitals = vitals
        self.save(update_fields=["vitals", "updated_at"])
