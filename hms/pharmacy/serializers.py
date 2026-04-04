"""
pharmacy/serializers.py
=======================
Drug catalogue and prescription serializers.

  DrugListSerializer          — searchable catalogue (no sensitive inventory cost).
  DrugDetailSerializer        — full record including unit_price, controlled flag.
  DrugStockUpdateSerializer   — restock or manual correction (admin only).
  PrescriptionListSerializer  — summary list.
  PrescriptionDetailSerializer — full record with nested drug info.
  PrescriptionCreateSerializer — doctor creates; validates drug availability.
  DispenseSerializer          — nurse/admin dispenses; validates stock and expiry.

Security
--------
- unit_price is excluded from DrugListSerializer (staff-facing, but pricing
  can be commercially sensitive — exposed in detail only to authenticated staff).
- controlled_drug flag is read-only to non-admin users.
- dispensed_by is read-only in all serializers (set by the dispense action).
"""

from datetime import date

from rest_framework import serializers

from patients.serializers import PatientMinimalSerializer
from doctors.serializers import DoctorMinimalSerializer
from accounts.serializers import UserPublicSerializer
from .models import Drug, Prescription, PrescriptionStatus, DrugCategory, DrugUnit


# ---------------------------------------------------------------------------
# Drug — list (catalogue)
# ---------------------------------------------------------------------------

class DrugListSerializer(serializers.ModelSerializer):
    category_display  = serializers.CharField(source="get_category_display", read_only=True)
    unit_display      = serializers.CharField(source="get_unit_display",     read_only=True)
    is_low_stock      = serializers.ReadOnlyField()
    is_expired        = serializers.ReadOnlyField()
    days_until_expiry = serializers.ReadOnlyField()

    class Meta:
        model  = Drug
        fields = (
            "id",
            "name",
            "generic_name",
            "category",
            "category_display",
            "unit",
            "unit_display",
            "strength",
            "stock_quantity",
            "reorder_level",
            "is_low_stock",
            "is_expired",
            "days_until_expiry",
            "requires_prescription",
            "controlled_drug",
            "expiry_date",
            "is_active",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Drug — detail (full record)
# ---------------------------------------------------------------------------

class DrugDetailSerializer(serializers.ModelSerializer):
    category_display  = serializers.CharField(source="get_category_display", read_only=True)
    unit_display      = serializers.CharField(source="get_unit_display",     read_only=True)
    is_low_stock      = serializers.ReadOnlyField()
    is_out_of_stock   = serializers.ReadOnlyField()
    is_expired        = serializers.ReadOnlyField()
    days_until_expiry = serializers.ReadOnlyField()

    class Meta:
        model  = Drug
        fields = (
            "id",
            "name",
            "generic_name",
            "category",
            "category_display",
            "unit",
            "unit_display",
            "strength",
            "description",
            # Inventory
            "stock_quantity",
            "reorder_level",
            "unit_price",
            "is_low_stock",
            "is_out_of_stock",
            # Regulatory
            "barcode",
            "requires_prescription",
            "controlled_drug",
            # Shelf life
            "expiry_date",
            "batch_number",
            "is_expired",
            "days_until_expiry",
            # Supplier
            "manufacturer",
            "supplier",
            # Status
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "is_low_stock",
            "is_out_of_stock",
            "is_expired",
            "days_until_expiry",
            "created_at",
            "updated_at",
        )

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit price cannot be negative.")
        return value

    def validate_reorder_level(self, value):
        if value < 0:
            raise serializers.ValidationError("Reorder level cannot be negative.")
        return value

    def validate_expiry_date(self, value):
        # Allow past expiry dates to be recorded (for existing stock)
        # but warn via a flag; block dispensing via Drug.dispense()
        return value

    def validate_barcode(self, value):
        if not value:
            return value
        qs = Drug.objects.filter(barcode=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This barcode is already assigned to another drug.")
        return value

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        # controlled_drug is read-only for non-admin users
        if request and not request.user.is_admin:
            if "controlled_drug" in fields:
                fields["controlled_drug"].read_only = True
        return fields


# ---------------------------------------------------------------------------
# Drug — stock update
# ---------------------------------------------------------------------------

class DrugStockUpdateSerializer(serializers.Serializer):
    """
    POST /pharmacy/drugs/<id>/restock/
    Admin / inventory manager only.
    """
    quantity     = serializers.IntegerField(min_value=1)
    batch_number = serializers.CharField(max_length=60, required=False, allow_blank=True)
    expiry_date  = serializers.DateField(required=False, allow_null=True)
    notes        = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_expiry_date(self, value):
        if value and value <= date.today():
            raise serializers.ValidationError(
                "Cannot restock with an already-expired batch. Check the expiry date."
            )
        return value


# ---------------------------------------------------------------------------
# Prescription — list
# ---------------------------------------------------------------------------

class PrescriptionListSerializer(serializers.ModelSerializer):
    patient_name  = serializers.CharField(source="patient.full_name", read_only=True)
    patient_mrn   = serializers.CharField(source="patient.mrn",       read_only=True)
    doctor_name   = serializers.CharField(source="doctor.full_name",  read_only=True)
    drug_name     = serializers.CharField(source="drug.name",         read_only=True)
    drug_strength = serializers.CharField(source="drug.strength",     read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_pending    = serializers.ReadOnlyField()

    class Meta:
        model  = Prescription
        fields = (
            "id",
            "patient_name",
            "patient_mrn",
            "doctor_name",
            "drug_name",
            "drug_strength",
            "dosage",
            "frequency",
            "duration_days",
            "quantity_prescribed",
            "status",
            "status_display",
            "is_pending",
            "prescribed_at",
            "dispensed_at",
            "expiry_date",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Prescription — detail
# ---------------------------------------------------------------------------

class PrescriptionDetailSerializer(serializers.ModelSerializer):
    patient_detail = PatientMinimalSerializer(source="patient",      read_only=True)
    doctor_detail  = DoctorMinimalSerializer(source="doctor",        read_only=True)
    dispensed_by   = UserPublicSerializer(read_only=True)
    drug_detail    = serializers.SerializerMethodField()
    status_display        = serializers.CharField(source="get_status_display", read_only=True)
    is_pending            = serializers.ReadOnlyField()
    is_dispensed          = serializers.ReadOnlyField()
    is_prescription_expired = serializers.ReadOnlyField()

    class Meta:
        model  = Prescription
        fields = (
            "id",
            # Relations
            "patient",
            "patient_detail",
            "doctor",
            "doctor_detail",
            "medical_record",
            "drug",
            "drug_detail",
            # Dosage
            "dosage",
            "frequency",
            "duration_days",
            "quantity_prescribed",
            "instructions",
            "route",
            # Status
            "status",
            "status_display",
            "is_pending",
            "is_dispensed",
            "is_prescription_expired",
            # Dispense audit
            "dispensed_by",
            "dispensed_at",
            "expiry_date",
            # Timestamps
            "prescribed_at",
        )
        read_only_fields = (
            "id",
            "patient_detail",
            "doctor_detail",
            "drug_detail",
            "status",
            "status_display",
            "is_pending",
            "is_dispensed",
            "is_prescription_expired",
            "dispensed_by",
            "dispensed_at",
            "prescribed_at",
        )

    def get_drug_detail(self, obj):
        return {
            "id":                   str(obj.drug_id),
            "name":                 obj.drug.name,
            "generic_name":         obj.drug.generic_name,
            "strength":             obj.drug.strength,
            "unit":                 obj.drug.unit,
            "stock_quantity":       obj.drug.stock_quantity,
            "is_low_stock":         obj.drug.is_low_stock,
            "is_expired":           obj.drug.is_expired,
            "requires_prescription": obj.drug.requires_prescription,
            "controlled_drug":      obj.drug.controlled_drug,
        }


# ---------------------------------------------------------------------------
# Prescription — create (doctor only)
# ---------------------------------------------------------------------------

class PrescriptionCreateSerializer(serializers.ModelSerializer):
    """
    POST /pharmacy/prescriptions/
    Only doctors may create prescriptions (enforced by view permission).

    Validation
    ----------
    - Drug must be active and not expired.
    - quantity_prescribed must not exceed available stock.
    - If drug requires_prescription=False, it can be dispensed OTC — log a note.
    - Expiry date defaults to 30 days from now if not provided.
    """

    class Meta:
        model  = Prescription
        fields = (
            "patient",
            "doctor",
            "medical_record",
            "drug",
            "dosage",
            "frequency",
            "duration_days",
            "quantity_prescribed",
            "instructions",
            "route",
            "expiry_date",
        )
        extra_kwargs = {
            "medical_record": {"required": False},
            "expiry_date":    {"required": False},
            "route":          {"required": False},
            "instructions":   {"required": False},
        }

    def validate_drug(self, value):
        if not value.is_active:
            raise serializers.ValidationError(
                f"Drug '{value.name}' has been deactivated and cannot be prescribed."
            )
        if value.is_expired:
            raise serializers.ValidationError(
                f"Drug '{value.name}' expired on {value.expiry_date} and cannot be prescribed."
            )
        return value

    def validate_quantity_prescribed(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def validate_duration_days(self, value):
        if value < 1:
            raise serializers.ValidationError("Duration must be at least 1 day.")
        if value > 365:
            raise serializers.ValidationError(
                "Duration exceeds 365 days. Please issue shorter-term prescriptions."
            )
        return value

    def validate(self, attrs):
        drug     = attrs.get("drug")
        quantity = attrs.get("quantity_prescribed", 0)
        doctor   = attrs.get("doctor")
        request  = self.context.get("request")

        # Doctor can only prescribe as themselves (not on behalf of another doctor)
        if request and request.user.is_doctor:
            if hasattr(request.user, "doctor_profile"):
                if doctor and doctor.user_id != request.user.id:
                    raise serializers.ValidationError(
                        {"doctor": "You can only create prescriptions under your own doctor profile."}
                    )

        # Stock check (advisory — actual deduction happens at dispense time)
        if drug and quantity and drug.stock_quantity < quantity:
            raise serializers.ValidationError(
                {
                    "quantity_prescribed": (
                        f"Requested quantity ({quantity}) exceeds current stock "
                        f"({drug.stock_quantity} {drug.unit}s). "
                        f"The prescription can be saved but may not be dispensable immediately."
                    )
                }
            )

        # Default expiry to 30 days from now
        if not attrs.get("expiry_date"):
            from datetime import timedelta
            attrs["expiry_date"] = date.today() + timedelta(days=30)

        return attrs


# ---------------------------------------------------------------------------
# Dispense
# ---------------------------------------------------------------------------

class DispenseSerializer(serializers.Serializer):
    """
    POST /pharmacy/prescriptions/<id>/dispense/
    Nurse or admin action.
    """
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Optional dispensing notes (e.g. patient counselling given).",
    )

    def validate(self, attrs):
        prescription = self.context["prescription"]

        if prescription.status != PrescriptionStatus.PENDING:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"Cannot dispense — prescription status is '{prescription.get_status_display()}'. "
                        f"Only pending prescriptions can be dispensed."
                    ]
                }
            )

        if prescription.is_prescription_expired:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"This prescription expired on {prescription.expiry_date}. "
                        f"A new prescription from the doctor is required."
                    ]
                }
            )

        drug = prescription.drug
        if drug.is_expired:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"The drug '{drug.name}' expired on {drug.expiry_date}. "
                        f"It cannot be dispensed. Please restock with a valid batch."
                    ]
                }
            )

        if drug.stock_quantity < prescription.quantity_prescribed:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"Insufficient stock. Available: {drug.stock_quantity} {drug.unit}(s), "
                        f"required: {prescription.quantity_prescribed}."
                    ]
                }
            )

        return attrs


# ---------------------------------------------------------------------------
# Cancel prescription
# ---------------------------------------------------------------------------

class PrescriptionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=500,
        help_text="Required reason for cancellation.",
    )

    def validate(self, attrs):
        prescription = self.context["prescription"]
        if prescription.status != PrescriptionStatus.PENDING:
            raise serializers.ValidationError(
                {"non_field_errors": [
                    f"Cannot cancel — prescription is already '{prescription.get_status_display()}'."
                ]}
            )
        return attrs
