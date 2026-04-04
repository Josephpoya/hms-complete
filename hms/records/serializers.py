"""
records/serializers.py
======================
Electronic Health Record serializers.

  MedicalRecordListSerializer    — compact list (no SOAP content, no attachments).
  MedicalRecordDetailSerializer  — full SOAP record.
  MedicalRecordCreateSerializer  — doctor creates; links to appointment.
  MedicalRecordUpdateSerializer  — partial update; blocked on locked records.
  VitalsSerializer               — validates and merges vitals into the JSONB field.
  AttachmentSerializer           — represents one file reference in the JSONB array.
  AttachmentUploadSerializer     — validates a multipart file upload.
  RecordLockSerializer           — internal; called by Celery lock task.

Access control (enforced here AND in views)
-------------------------------------------
- is_hiv_positive on the Patient is not in any record serializer — access to
  sensitive flags goes via PatientDetailSerializer with role-based filtering.
- Attachment list is visible to all clinical staff.
- old_value / new_value in AuditLog are admin-readable only (AuditLog serializer
  below is admin-only in the view layer).

Locked record protection
------------------------
MedicalRecordUpdateSerializer.validate() raises a 400 if is_locked=True.
The model's save() also raises ValidationError as a second layer.
"""

from rest_framework import serializers

from patients.serializers import PatientMinimalSerializer
from doctors.serializers import DoctorMinimalSerializer
from accounts.serializers import UserPublicSerializer
from .models import MedicalRecord


# ---------------------------------------------------------------------------
# Vitals
# ---------------------------------------------------------------------------

class VitalsSerializer(serializers.Serializer):
    """
    Validates the structured vitals JSONB.
    All fields optional — a consultation may only record selected measurements.
    """
    bp_systolic      = serializers.IntegerField(min_value=40, max_value=300, required=False, allow_null=True,
                                                help_text="Systolic blood pressure (mmHg).")
    bp_diastolic     = serializers.IntegerField(min_value=20, max_value=200, required=False, allow_null=True,
                                                help_text="Diastolic blood pressure (mmHg).")
    pulse            = serializers.IntegerField(min_value=20, max_value=300, required=False, allow_null=True,
                                                help_text="Heart rate (bpm).")
    temperature      = serializers.DecimalField(max_digits=4, decimal_places=1,
                                                min_value=30, max_value=45,
                                                required=False, allow_null=True,
                                                help_text="Body temperature (°C).")
    spo2             = serializers.IntegerField(min_value=50, max_value=100, required=False, allow_null=True,
                                                help_text="Oxygen saturation (%).")
    respiratory_rate = serializers.IntegerField(min_value=5, max_value=60, required=False, allow_null=True,
                                                help_text="Breaths per minute.")
    weight_kg        = serializers.DecimalField(max_digits=5, decimal_places=1,
                                                min_value=0.5, max_value=500,
                                                required=False, allow_null=True,
                                                help_text="Weight in kilograms.")
    height_cm        = serializers.DecimalField(max_digits=5, decimal_places=1,
                                                min_value=20, max_value=300,
                                                required=False, allow_null=True,
                                                help_text="Height in centimetres.")
    bmi              = serializers.DecimalField(max_digits=4, decimal_places=1,
                                                min_value=5, max_value=100,
                                                required=False, allow_null=True,
                                                help_text="Body mass index (auto-computed if weight+height given).")
    blood_glucose    = serializers.DecimalField(max_digits=5, decimal_places=1,
                                                min_value=0, max_value=100,
                                                required=False, allow_null=True,
                                                help_text="Blood glucose (mmol/L).")
    urine_output     = serializers.DecimalField(max_digits=7, decimal_places=1,
                                                min_value=0, max_value=100000,
                                                required=False, allow_null=True,
                                                help_text="Urine output (ml).")

    def validate(self, attrs):
        # Auto-compute BMI if weight and height are both provided
        weight = attrs.get("weight_kg")
        height = attrs.get("height_cm")
        if weight and height and not attrs.get("bmi"):
            height_m = float(height) / 100
            attrs["bmi"] = round(float(weight) / (height_m ** 2), 1)

        # Pulse pressure sanity check
        systolic  = attrs.get("bp_systolic")
        diastolic = attrs.get("bp_diastolic")
        if systolic and diastolic:
            if diastolic >= systolic:
                raise serializers.ValidationError(
                    {"bp_diastolic": "Diastolic pressure must be lower than systolic pressure."}
                )
            pulse_pressure = systolic - diastolic
            if pulse_pressure > 100:
                # Clinically possible but warrants a note
                pass  # surfaced to the UI via a warning flag in future

        # Remove None values so the JSONB only stores recorded measurements
        return {k: v for k, v in attrs.items() if v is not None}


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------

class AttachmentSerializer(serializers.Serializer):
    """Read representation of one entry in the JSONB attachments array."""
    key          = serializers.CharField(read_only=True)
    filename     = serializers.CharField(read_only=True)
    content_type = serializers.CharField(read_only=True)
    size         = serializers.IntegerField(read_only=True, help_text="File size in bytes.")
    uploaded_at  = serializers.DateTimeField(read_only=True)


class AttachmentUploadSerializer(serializers.Serializer):
    """Validates a multipart file upload before it is sent to S3."""
    file = serializers.FileField(
        max_length=255,
        help_text="Supported formats: PDF, JPEG, PNG, DICOM.",
    )

    ALLOWED_TYPES = {
        "application/pdf":  ".pdf",
        "image/jpeg":       ".jpg",
        "image/png":        ".png",
        "application/dicom": ".dcm",
    }
    MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    def validate_file(self, value):
        if value.size > self.MAX_SIZE_BYTES:
            raise serializers.ValidationError(
                f"File too large ({value.size // (1024*1024)} MB). Maximum is 25 MB."
            )
        content_type = value.content_type
        if content_type not in self.ALLOWED_TYPES:
            raise serializers.ValidationError(
                f"Unsupported file type '{content_type}'. "
                f"Allowed types: {', '.join(self.ALLOWED_TYPES.keys())}."
            )
        return value


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class MedicalRecordListSerializer(serializers.ModelSerializer):
    patient_name        = serializers.CharField(source="patient.full_name",  read_only=True)
    patient_mrn         = serializers.CharField(source="patient.mrn",        read_only=True)
    doctor_name         = serializers.CharField(source="doctor.full_name",   read_only=True, default=None)
    is_complete         = serializers.ReadOnlyField()
    attachment_count    = serializers.ReadOnlyField()
    is_within_edit_window = serializers.ReadOnlyField()

    class Meta:
        model  = MedicalRecord
        fields = (
            "id",
            "patient_name",
            "patient_mrn",
            "doctor_name",
            "icd10_code",
            "icd10_description",
            "recorded_at",
            "is_complete",
            "is_locked",
            "attachment_count",
            "is_within_edit_window",
            "follow_up_date",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Detail — read
# ---------------------------------------------------------------------------

class MedicalRecordDetailSerializer(serializers.ModelSerializer):
    patient_detail  = PatientMinimalSerializer(source="patient", read_only=True)
    doctor_detail   = DoctorMinimalSerializer(source="doctor",   read_only=True)
    appointment_info = serializers.SerializerMethodField()
    vitals_display  = VitalsSerializer(source="vitals", read_only=True)
    attachments_list = AttachmentSerializer(source="attachments", many=True, read_only=True)
    prescriptions_count = serializers.SerializerMethodField()
    is_complete         = serializers.ReadOnlyField()
    is_within_edit_window = serializers.ReadOnlyField()

    class Meta:
        model  = MedicalRecord
        fields = (
            "id",
            # Relations
            "patient",
            "patient_detail",
            "doctor",
            "doctor_detail",
            "appointment",
            "appointment_info",
            # SOAP
            "subjective",
            "objective",
            "assessment",
            "plan",
            # Diagnosis
            "icd10_code",
            "icd10_description",
            "secondary_diagnoses",
            # Vitals
            "vitals",
            "vitals_display",
            # Attachments
            "attachments",
            "attachments_list",
            # Follow-up
            "follow_up_date",
            "referral_to",
            "referral_notes",
            # Prescriptions
            "prescriptions_count",
            # Completeness
            "is_complete",
            "is_within_edit_window",
            # Lock
            "is_locked",
            "locked_at",
            # Timestamps
            "recorded_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_appointment_info(self, obj):
        if not obj.appointment_id:
            return None
        apt = obj.appointment
        return {
            "id":            str(apt.id),
            "scheduled_at":  apt.scheduled_at,
            "type":          apt.appointment_type,
            "status":        apt.status,
        }

    def get_prescriptions_count(self, obj):
        return obj.prescriptions.count() if obj.pk else 0


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class MedicalRecordCreateSerializer(serializers.ModelSerializer):
    """
    POST /records/
    Doctor-only. Appointment field links this note to a specific encounter.
    """
    vitals_input = VitalsSerializer(write_only=True, required=False)

    class Meta:
        model  = MedicalRecord
        fields = (
            "patient",
            "doctor",
            "appointment",
            # SOAP
            "subjective",
            "objective",
            "assessment",
            "plan",
            # Diagnosis
            "icd10_code",
            "icd10_description",
            "secondary_diagnoses",
            # Vitals (input via nested serializer for validation)
            "vitals_input",
            # Follow-up
            "follow_up_date",
            "referral_to",
            "referral_notes",
        )
        extra_kwargs = {
            "appointment":        {"required": False},
            "subjective":         {"required": False},
            "objective":          {"required": False},
            "assessment":         {"required": False},
            "plan":               {"required": False},
            "icd10_code":         {"required": False},
            "icd10_description":  {"required": False},
            "secondary_diagnoses": {"required": False},
            "follow_up_date":     {"required": False},
            "referral_to":        {"required": False},
            "referral_notes":     {"required": False},
        }

    def validate_icd10_code(self, value):
        if not value:
            return value
        import re
        # ICD-10 format: letter + 2 digits, optional dot + 1-4 alphanums
        if not re.match(r"^[A-Z]\d{2}(\.\d{1,4})?$", value.upper()):
            raise serializers.ValidationError(
                f"'{value}' does not look like a valid ICD-10 code (e.g. J06.9, A09, K21.0)."
            )
        return value.upper()

    def validate_doctor(self, value):
        request = self.context.get("request")
        if request and request.user.is_doctor:
            if not hasattr(request.user, "doctor_profile"):
                raise serializers.ValidationError(
                    "Your account does not have a doctor profile. Contact the administrator."
                )
            if value.user_id != request.user.id:
                raise serializers.ValidationError(
                    "You can only create records under your own doctor profile."
                )
        return value

    def validate_appointment(self, value):
        if value and hasattr(value, "medical_record"):
            raise serializers.ValidationError(
                "A medical record already exists for this appointment."
            )
        return value

    def validate_secondary_diagnoses(self, value):
        if not value:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError("Secondary diagnoses must be a list.")
        for item in value:
            if not isinstance(item, dict) or "code" not in item:
                raise serializers.ValidationError(
                    "Each secondary diagnosis must be an object with at least a 'code' key."
                )
        return value

    def validate(self, attrs):
        # Appointment patient must match record patient
        appointment = attrs.get("appointment")
        patient     = attrs.get("patient")
        if appointment and patient and appointment.patient_id != patient.id:
            raise serializers.ValidationError(
                {"appointment": "The appointment does not belong to the selected patient."}
            )
        return attrs

    def create(self, validated_data):
        vitals_input = validated_data.pop("vitals_input", None)
        if vitals_input:
            validated_data["vitals"] = vitals_input
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class MedicalRecordUpdateSerializer(serializers.ModelSerializer):
    """
    PATCH /records/<id>/
    Only the authoring doctor may update; only within the edit window (24h).
    Vitals updated via VitalsSerializer validation then merged.
    """
    vitals_input = VitalsSerializer(write_only=True, required=False)

    class Meta:
        model  = MedicalRecord
        fields = (
            # SOAP
            "subjective",
            "objective",
            "assessment",
            "plan",
            # Diagnosis
            "icd10_code",
            "icd10_description",
            "secondary_diagnoses",
            # Vitals
            "vitals_input",
            # Follow-up
            "follow_up_date",
            "referral_to",
            "referral_notes",
        )
        extra_kwargs = {f: {"required": False} for f in fields.__iter__() if isinstance(f, str)}

    def validate(self, attrs):
        if self.instance and self.instance.is_locked:
            raise serializers.ValidationError(
                "This record has been locked (24h window has passed) and cannot be modified. "
                "Contact the administrator if a clinical amendment is required."
            )
        if self.instance and not self.instance.is_within_edit_window:
            raise serializers.ValidationError(
                "The 24-hour editing window for this record has closed. "
                "The record will be locked shortly."
            )
        return attrs

    def validate_icd10_code(self, value):
        if not value:
            return value
        import re
        if not re.match(r"^[A-Z]\d{2}(\.\d{1,4})?$", value.upper()):
            raise serializers.ValidationError(
                f"'{value}' is not a valid ICD-10 code format (e.g. J06.9)."
            )
        return value.upper()

    def update(self, instance, validated_data):
        vitals_input = validated_data.pop("vitals_input", None)
        if vitals_input:
            # Merge into existing vitals rather than replacing
            existing = dict(instance.vitals or {})
            existing.update(vitals_input)
            validated_data["vitals"] = existing
        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Audit log (admin-only read)
# ---------------------------------------------------------------------------

class AuditLogSerializer(serializers.Serializer):
    """
    Read-only representation of an AuditLog entry.
    Rendered by the admin-only AuditLogListView.
    old_value and new_value are only shown to admins (enforced in get_fields).
    """
    id                  = serializers.UUIDField(read_only=True)
    user_email_snapshot = serializers.CharField(read_only=True)
    user_role_snapshot  = serializers.CharField(read_only=True)
    action              = serializers.CharField(read_only=True)
    table_name          = serializers.CharField(read_only=True)
    record_id           = serializers.UUIDField(read_only=True, allow_null=True)
    old_value           = serializers.JSONField(read_only=True, allow_null=True)
    new_value           = serializers.JSONField(read_only=True, allow_null=True)
    ip_address          = serializers.CharField(read_only=True, allow_null=True)
    created_at          = serializers.DateTimeField(read_only=True)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        # Hide raw JSON diffs from non-super-admins
        if not (request and request.user.is_admin and request.user.is_staff):
            fields.pop("old_value", None)
            fields.pop("new_value", None)
        return fields
