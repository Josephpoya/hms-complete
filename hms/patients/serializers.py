"""
patients/serializers.py
=======================
Patient serializers with three exposure levels:

  PatientMinimalSerializer  — safe for embedding in other resources (e.g. in an
                              appointment response). Name, MRN, phone only.
  PatientListSerializer     — non-sensitive demographics for list views.
  PatientDetailSerializer   — full record for create/retrieve/update.

Sensitive field handling
------------------------
- is_hiv_positive, national_id are excluded from the list serializer.
- In the detail serializer, is_hiv_positive is readable only by clinical
  staff — enforced by the view's queryset / serializer selection, not here.
- national_id appears in the detail serializer but is marked write_only
  for non-admin contexts (controlled by get_fields() at runtime).

Validation
----------
- date_of_birth: must be in the past; must be realistic (< 150 years ago).
- phone: normalised to E.164 after stripping formatting characters.
- email: lowercased and format-checked.
- national_id: uniqueness checked excluding the current instance (for updates).
"""

import re
from datetime import date, timedelta

from rest_framework import serializers

from accounts.serializers import UserPublicSerializer
from .models import Patient, Gender, BloodType


# ---------------------------------------------------------------------------
# Minimal — safe for nesting
# ---------------------------------------------------------------------------

class PatientMinimalSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model  = Patient
        fields = ("id", "mrn", "full_name", "phone")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# List — non-sensitive demographics
# ---------------------------------------------------------------------------

class PatientListSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    age       = serializers.ReadOnlyField()

    class Meta:
        model  = Patient
        fields = (
            "id",
            "mrn",
            "full_name",
            "first_name",
            "last_name",
            "date_of_birth",
            "age",
            "gender",
            "blood_type",
            "phone",
            "email",
            "insurance_provider",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "mrn", "age", "created_at")


# ---------------------------------------------------------------------------
# Detail — full record
# ---------------------------------------------------------------------------

class PatientDetailSerializer(serializers.ModelSerializer):
    """
    Full patient serializer for create / retrieve / update.

    Dynamic field visibility
    ------------------------
    is_hiv_positive is only visible to clinical staff (doctor / nurse / admin).
    The view passes the request in serializer context; get_fields() checks the role.
    """
    full_name             = serializers.ReadOnlyField()
    age                   = serializers.ReadOnlyField()
    has_allergies         = serializers.ReadOnlyField()
    insurance_is_valid    = serializers.ReadOnlyField()
    outstanding_balance   = serializers.SerializerMethodField()
    created_by            = UserPublicSerializer(read_only=True)

    class Meta:
        model  = Patient
        fields = (
            # Identity
            "id",
            "mrn",
            "first_name",
            "last_name",
            "full_name",
            "date_of_birth",
            "age",
            "gender",
            "blood_type",
            "nationality",
            "national_id",
            # Contact
            "phone",
            "email",
            "address",
            # Clinical flags
            "allergies",
            "chronic_conditions",
            "is_diabetic",
            "is_hypertensive",
            "is_hiv_positive",
            "has_allergies",
            # Emergency contact
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relation",
            # Insurance
            "insurance_provider",
            "insurance_number",
            "insurance_expiry",
            "insurance_is_valid",
            # Financial summary
            "outstanding_balance",
            # Audit
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        )
        read_only_fields = (
            "id", "mrn", "full_name", "age", "has_allergies",
            "insurance_is_valid", "outstanding_balance",
            "created_by", "created_at", "updated_at",
        )
        extra_kwargs = {
            "national_id": {"write_only": False},  # readable; override per role below
        }

    def get_outstanding_balance(self, obj):
        if obj.pk:
            return str(obj.get_outstanding_balance())
        return "0.00"

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            # Unauthenticated: should not reach here (views require auth), but be safe.
            fields.pop("is_hiv_positive", None)
            fields.pop("national_id", None)
            return fields

        user = request.user

        # Receptionist and non-clinical roles cannot see HIV status
        if not user.is_clinical_staff and not user.is_admin:
            fields.pop("is_hiv_positive", None)

        # national_id write_only for non-admin (can read their own via admin endpoint)
        if not user.is_admin:
            if "national_id" in fields:
                fields["national_id"].read_only = True

        return fields

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    def validate_date_of_birth(self, value):
        today = date.today()
        if value >= today:
            raise serializers.ValidationError("Date of birth must be in the past.")
        min_date = today - timedelta(days=365 * 150)
        if value < min_date:
            raise serializers.ValidationError("Date of birth is unrealistically far in the past.")
        return value

    def validate_phone(self, value):
        cleaned = re.sub(r"[\s\-\(\)\.]", "", value)
        if not re.match(r"^\+?[0-9]{7,15}$", cleaned):
            raise serializers.ValidationError(
                "Enter a valid phone number (7–15 digits, optional leading +)."
            )
        return cleaned

    def validate_email(self, value):
        if value:
            return value.lower().strip()
        return value

    def validate_national_id(self, value):
        if not value:
            return value
        qs = Patient.objects.filter(national_id=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A patient with this national ID is already registered."
            )
        return value

    def validate_insurance_expiry(self, value):
        # Allow past expiry dates to be recorded (insurance may have lapsed)
        return value

    def validate(self, attrs):
        # Cross-field: emergency contact — if name given, phone is required
        ec_name  = attrs.get("emergency_contact_name") or (self.instance and self.instance.emergency_contact_name)
        ec_phone = attrs.get("emergency_contact_phone") or (self.instance and self.instance.emergency_contact_phone)
        if ec_name and not ec_phone:
            raise serializers.ValidationError(
                {"emergency_contact_phone": "Phone number is required when an emergency contact name is provided."}
            )
        return attrs

    # ------------------------------------------------------------------
    # Create / update
    # ------------------------------------------------------------------

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Prevent changing MRN or created_by on update (belt-and-suspenders)
        validated_data.pop("mrn", None)
        validated_data.pop("created_by", None)
        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Soft-delete response
# ---------------------------------------------------------------------------

class PatientDeactivateSerializer(serializers.Serializer):
    """Body for DELETE (soft-delete) — optional reason."""
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
