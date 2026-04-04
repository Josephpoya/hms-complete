"""
billing/serializers.py
======================
Invoice and line-item serializers.

  InvoiceItemSerializer        — line item CRUD; validates editable-only constraint.
  InvoiceListSerializer        — summary list (no items).
  InvoiceDetailSerializer      — full invoice with nested items (read); flat for write.
  InvoiceCreateSerializer      — creation with optional inline items.
  InvoiceActionSerializer      — named lifecycle actions (issue / record_payment / void).
  PaymentSerializer            — record a full or partial payment.

Financial validation
--------------------
- unit_price >= 0, quantity >= 1 (InvoiceItem).
- discount_amount cannot exceed subtotal.
- tax_rate between 0 and 100.
- Cannot add/change/delete items on a non-draft invoice.
- Cannot make payment on a draft or voided invoice.
- Payment amount cannot exceed balance_due.
"""

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from patients.serializers import PatientMinimalSerializer
from appointments.serializers import AppointmentListSerializer
from accounts.serializers import UserPublicSerializer
from .models import Invoice, InvoiceItem, InvoiceStatus, ItemType, EDITABLE_STATUSES


# ---------------------------------------------------------------------------
# Invoice Item
# ---------------------------------------------------------------------------

class InvoiceItemSerializer(serializers.ModelSerializer):
    line_total    = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    type_display  = serializers.CharField(source="get_item_type_display", read_only=True)

    class Meta:
        model  = InvoiceItem
        fields = (
            "id",
            "description",
            "item_type",
            "type_display",
            "unit_price",
            "quantity",
            "line_total",
            "reference_id",
        )
        read_only_fields = ("id", "line_total", "type_display")
        extra_kwargs = {
            "unit_price": {"min_value": Decimal("0")},
            "quantity":   {"min_value": 1},
        }

    def validate_unit_price(self, value):
        if value < Decimal("0"):
            raise serializers.ValidationError("Unit price cannot be negative.")
        return value

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def validate(self, attrs):
        # Guard: invoice must be in draft
        invoice = self.context.get("invoice") or (self.instance and self.instance.invoice)
        if invoice and invoice.status not in EDITABLE_STATUSES:
            raise serializers.ValidationError(
                f"Cannot modify items on a '{invoice.get_status_display()}' invoice. "
                f"Only draft invoices can be edited."
            )
        return attrs


class InvoiceItemWriteSerializer(InvoiceItemSerializer):
    """Flat write serializer — used when creating items standalone via /invoices/<id>/items/."""
    class Meta(InvoiceItemSerializer.Meta):
        # invoice is set in the view via perform_create
        fields = tuple(f for f in InvoiceItemSerializer.Meta.fields if f != "id")
        read_only_fields = ("line_total", "type_display")


# ---------------------------------------------------------------------------
# Invoice — list
# ---------------------------------------------------------------------------

class InvoiceListSerializer(serializers.ModelSerializer):
    patient_name    = serializers.CharField(source="patient.full_name", read_only=True)
    patient_mrn     = serializers.CharField(source="patient.mrn",       read_only=True)
    status_display  = serializers.CharField(source="get_status_display", read_only=True)
    balance_due     = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_overdue      = serializers.ReadOnlyField()

    class Meta:
        model  = Invoice
        fields = (
            "id",
            "invoice_number",
            "patient_name",
            "patient_mrn",
            "status",
            "status_display",
            "subtotal",
            "tax_amount",
            "discount_amount",
            "total_amount",
            "amount_paid",
            "balance_due",
            "currency",
            "is_overdue",
            "issued_at",
            "due_at",
            "paid_at",
            "created_at",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Invoice — detail (read)
# ---------------------------------------------------------------------------

class InvoiceDetailSerializer(serializers.ModelSerializer):
    patient_detail   = PatientMinimalSerializer(source="patient",     read_only=True)
    appointment_info = serializers.SerializerMethodField()
    created_by       = UserPublicSerializer(read_only=True)
    items            = InvoiceItemSerializer(many=True, read_only=True)
    status_display   = serializers.CharField(source="get_status_display", read_only=True)
    balance_due      = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_overdue       = serializers.ReadOnlyField()
    is_fully_paid    = serializers.ReadOnlyField()
    is_editable      = serializers.ReadOnlyField()

    class Meta:
        model  = Invoice
        fields = (
            "id",
            "invoice_number",
            # Relations
            "patient",
            "patient_detail",
            "appointment",
            "appointment_info",
            "created_by",
            # Status
            "status",
            "status_display",
            "is_editable",
            # Financials
            "subtotal",
            "tax_rate",
            "tax_amount",
            "discount_amount",
            "total_amount",
            "amount_paid",
            "balance_due",
            "currency",
            "is_overdue",
            "is_fully_paid",
            # Content
            "notes",
            "items",
            # Dates
            "issued_at",
            "due_at",
            "paid_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_appointment_info(self, obj):
        if not obj.appointment_id:
            return None
        return {
            "id":           str(obj.appointment_id),
            "scheduled_at": obj.appointment.scheduled_at,
            "doctor_name":  obj.appointment.doctor.full_name,
        }


# ---------------------------------------------------------------------------
# Invoice — create
# ---------------------------------------------------------------------------

class InvoiceCreateSerializer(serializers.ModelSerializer):
    """
    Accepts optional inline items at creation.
    Items can also be added later via the /invoices/<id>/items/ endpoint.
    """
    items = InvoiceItemSerializer(many=True, required=False)

    class Meta:
        model  = Invoice
        fields = (
            "patient",
            "appointment",
            "tax_rate",
            "discount_amount",
            "currency",
            "notes",
            "items",
        )
        extra_kwargs = {
            "appointment": {"required": False},
        }

    def validate_tax_rate(self, value):
        if not (Decimal("0") <= value <= Decimal("100")):
            raise serializers.ValidationError("Tax rate must be between 0 and 100.")
        return value

    def validate_discount_amount(self, value):
        if value < Decimal("0"):
            raise serializers.ValidationError("Discount amount cannot be negative.")
        return value

    def validate_currency(self, value):
        value = value.upper()
        # Basic ISO 4217 length check — full validation would use a currency library
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Currency must be a 3-letter ISO 4217 code (e.g. UGX, USD, KES).")
        return value

    def validate(self, attrs):
        # Appointment must belong to the same patient
        appointment = attrs.get("appointment")
        patient     = attrs.get("patient")
        if appointment and appointment.patient_id != patient.id:
            raise serializers.ValidationError(
                {"appointment": "The appointment does not belong to the selected patient."}
            )
        # One invoice per appointment
        if appointment and hasattr(appointment, "invoice"):
            raise serializers.ValidationError(
                {"appointment": "An invoice already exists for this appointment."}
            )
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request    = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user

        invoice = Invoice.objects.create(**validated_data)

        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)

        invoice.refresh_from_db()
        return invoice


# ---------------------------------------------------------------------------
# Invoice — update (draft only)
# ---------------------------------------------------------------------------

class InvoiceUpdateSerializer(serializers.ModelSerializer):
    """
    Only fields that make sense to change on a draft invoice.
    patient and appointment cannot be changed after creation.
    """
    class Meta:
        model  = Invoice
        fields = ("tax_rate", "discount_amount", "currency", "notes")

    def validate(self, attrs):
        if self.instance and not self.instance.is_editable:
            raise serializers.ValidationError(
                f"Only draft invoices can be updated. "
                f"This invoice is '{self.instance.get_status_display()}'."
            )
        return attrs

    def validate_discount_amount(self, value):
        if value < Decimal("0"):
            raise serializers.ValidationError("Discount amount cannot be negative.")
        # Check against subtotal if instance exists and has items
        if self.instance:
            if value > self.instance.subtotal:
                raise serializers.ValidationError(
                    f"Discount ({value}) cannot exceed the subtotal ({self.instance.subtotal})."
                )
        return value


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class InvoiceActionSerializer(serializers.Serializer):
    """
    POST /billing/invoices/<id>/action/
    Named lifecycle transitions. Each action calls the corresponding model method.
    """
    ACTION_CHOICES = [
        ("issue",        "Issue invoice"),
        ("mark_overdue", "Mark as overdue"),
        ("void",         "Void invoice"),
    ]
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    notes  = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        invoice = self.context["invoice"]
        action  = attrs["action"]

        # Validate action is legal for current status
        VALID_ACTIONS = {
            "issue":        [InvoiceStatus.DRAFT],
            "mark_overdue": [InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
            "void":         [InvoiceStatus.DRAFT, InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE],
        }
        allowed_statuses = VALID_ACTIONS.get(action, [])
        if invoice.status not in allowed_statuses:
            raise serializers.ValidationError(
                {
                    "action": (
                        f"Cannot perform '{action}' on a '{invoice.get_status_display()}' invoice. "
                        f"Allowed when status is: {allowed_statuses}."
                    )
                }
            )

        if action == "issue" and not invoice.items.exists():
            raise serializers.ValidationError(
                {"action": "Cannot issue an invoice with no line items."}
            )

        return attrs


class PaymentSerializer(serializers.Serializer):
    """
    POST /billing/invoices/<id>/payment/
    Record a full or partial payment against an invoice.
    """
    amount          = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method  = serializers.ChoiceField(
        choices=[
            ("cash",          "Cash"),
            ("card",          "Card"),
            ("mobile_money",  "Mobile Money"),
            ("insurance",     "Insurance"),
            ("bank_transfer", "Bank Transfer"),
        ]
    )
    reference_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes            = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def validate(self, attrs):
        invoice = self.context["invoice"]
        amount  = attrs["amount"]

        if invoice.status not in [InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]:
            raise serializers.ValidationError(
                {"amount": f"Cannot accept payment on a '{invoice.get_status_display()}' invoice."}
            )
        if amount > invoice.balance_due:
            raise serializers.ValidationError(
                {
                    "amount": (
                        f"Payment amount ({amount}) exceeds the balance due ({invoice.balance_due}). "
                        f"Maximum accepted: {invoice.balance_due}."
                    )
                }
            )
        return attrs
