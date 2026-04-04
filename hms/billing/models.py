"""
billing/models.py
=================
Invoice header + line items, with automatic total recomputation.

Design decisions:
  - NUMERIC(12,2) for all monetary values — never float.
  - total_amount is recomputed from items on every save (application layer).
    A DB trigger or GENERATED column can back this up for extra safety.
  - InvoiceItem.save() cascades a recalculate up to its parent Invoice.
  - Invoice number uses a PostgreSQL sequence for collision-safe generation.
  - Status machine: draft → issued → (partially_paid | paid | overdue | voided).
    Actions exposed as named methods, not arbitrary status writes.
  - Currency stored per invoice (ISO 4217) to support multi-currency environments.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class InvoiceStatus(models.TextChoices):
    DRAFT          = "draft",          "Draft"
    ISSUED         = "issued",         "Issued"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID           = "paid",           "Paid"
    VOIDED         = "voided",         "Voided"
    OVERDUE        = "overdue",        "Overdue"


class ItemType(models.TextChoices):
    CONSULTATION = "consultation", "Consultation"
    PROCEDURE    = "procedure",    "Procedure"
    LAB          = "lab",          "Laboratory"
    PHARMACY     = "pharmacy",     "Pharmacy"
    SUPPLY       = "supply",       "Medical Supply"
    RADIOLOGY    = "radiology",    "Radiology"
    NURSING      = "nursing",      "Nursing Care"
    OTHER        = "other",        "Other"


EDITABLE_STATUSES = frozenset({InvoiceStatus.DRAFT})
PAYABLE_STATUSES  = frozenset({InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE})


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class InvoiceManager(models.Manager):
    def outstanding(self):
        return self.get_queryset().filter(status__in=PAYABLE_STATUSES)

    def for_patient(self, patient_id):
        return self.get_queryset().filter(patient_id=patient_id)

    def overdue(self):
        return self.get_queryset().filter(
            status=InvoiceStatus.ISSUED,
            due_at__lt=timezone.now(),
        )


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class Invoice(models.Model):
    """
    Billing document — one per patient encounter (or stand-alone charge).

    Relationships
    -------------
    → patients.Patient           : the billed patient.
    → appointments.Appointment   : the encounter that triggered this invoice (optional).
    → accounts.User (created_by) : receptionist / admin who raised it.
    ← InvoiceItem                : line items (CASCADE delete).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice_number = models.CharField(
        max_length=30, unique=True, db_index=True, editable=False,
        help_text="Auto-generated: INV-YYYY-NNNNNN.",
    )

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="invoices",
        db_index=True,
    )
    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice",
        help_text="The encounter this invoice was generated from.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_invoices",
    )

    # ---- Status -----------------------------------------------------------
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        db_index=True,
    )

    # ---- Financials -------------------------------------------------------
    subtotal        = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Sum of all line item totals before tax/discount.",
    )
    tax_rate        = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Tax percentage e.g. 18.00 for 18% VAT.",
    )
    tax_amount      = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_amount    = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="subtotal + tax_amount - discount_amount. Recomputed on every save.",
    )
    amount_paid     = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Running total of payments received.",
    )

    currency = models.CharField(max_length=3, default="UGX", help_text="ISO 4217.")
    notes    = models.TextField(blank=True)

    # ---- Dates ------------------------------------------------------------
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at    = models.DateTimeField(null=True, blank=True)
    paid_at   = models.DateTimeField(null=True, blank=True)

    # ---- Timestamps -------------------------------------------------------
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = InvoiceManager()

    class Meta:
        db_table            = "billing_invoice"
        verbose_name        = "Invoice"
        verbose_name_plural = "Invoices"
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "status"],  name="idx_invoice_patient_status"),
            models.Index(fields=["status", "due_at"],   name="idx_invoice_status_due"),
            models.Index(fields=["invoice_number"],     name="idx_invoice_number"),
        ]

    def __str__(self):
        return f"{self.invoice_number} — {self.patient} [{self.get_status_display()}]"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def balance_due(self):
        return max(self.total_amount - self.amount_paid, Decimal("0.00"))

    @property
    def is_fully_paid(self):
        return self.balance_due == Decimal("0.00")

    @property
    def is_editable(self):
        return self.status in EDITABLE_STATUSES

    @property
    def is_overdue(self):
        return (
            self.status in PAYABLE_STATUSES
            and self.due_at
            and self.due_at < timezone.now()
        )

    # ------------------------------------------------------------------
    # Total computation
    # ------------------------------------------------------------------

    def recalculate_totals(self):
        """
        Recompute subtotal from line items, then derive tax and total.
        Call this whenever items change; also called in save().
        """
        subtotal = (
            self.items.aggregate(s=models.Sum("line_total"))["s"]
            or Decimal("0.00")
        )
        self.subtotal     = subtotal
        self.tax_amount   = (subtotal * self.tax_rate / 100).quantize(Decimal("0.01"))
        self.total_amount = (
            subtotal + self.tax_amount - self.discount_amount
        ).quantize(Decimal("0.01"))

    # ------------------------------------------------------------------
    # Lifecycle actions
    # ------------------------------------------------------------------

    def issue(self, due_days=30):
        if self.status != InvoiceStatus.DRAFT:
            raise ValidationError("Only draft invoices can be issued.")
        if not self.items.exists():
            raise ValidationError("Cannot issue an invoice with no line items.")
        from datetime import timedelta
        self.status    = InvoiceStatus.ISSUED
        self.issued_at = timezone.now()
        self.due_at    = timezone.now() + timedelta(days=due_days)
        self.save(update_fields=["status", "issued_at", "due_at", "updated_at"])

    def record_payment(self, amount):
        """Record a partial or full payment."""
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")
        if self.status not in PAYABLE_STATUSES:
            raise ValidationError(f"Cannot accept payment on a '{self.status}' invoice.")
        self.amount_paid += amount
        if self.is_fully_paid:
            self.status  = InvoiceStatus.PAID
            self.paid_at = timezone.now()
        else:
            self.status = InvoiceStatus.PARTIALLY_PAID
        self.save(update_fields=["amount_paid", "status", "paid_at", "updated_at"])

    def mark_overdue(self):
        if self.status not in PAYABLE_STATUSES:
            raise ValidationError(f"Cannot mark '{self.status}' invoice as overdue.")
        self.status = InvoiceStatus.OVERDUE
        self.save(update_fields=["status", "updated_at"])

    def void(self):
        if self.status == InvoiceStatus.PAID:
            raise ValidationError("Cannot void a paid invoice. Issue a credit note instead.")
        if self.status == InvoiceStatus.VOIDED:
            raise ValidationError("Invoice is already voided.")
        self.status = InvoiceStatus.VOIDED
        self.save(update_fields=["status", "updated_at"])

    # ------------------------------------------------------------------
    # Save / invoice number generation
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        # Only recompute totals when not doing a status-only update
        update_fields = kwargs.get("update_fields")
        if not update_fields or "subtotal" in update_fields:
            if self.pk:
                self.recalculate_totals()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_invoice_number(cls):
        prefix = getattr(settings, "HMS_INVOICE_PREFIX", "INV")
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval('billing_invoice_seq')")
            seq = cursor.fetchone()[0]
        year = timezone.now().year
        return f"{prefix}-{year}-{seq:06d}"


# ---------------------------------------------------------------------------
# InvoiceItem
# ---------------------------------------------------------------------------

class InvoiceItem(models.Model):
    """
    A single charge line on an Invoice.

    line_total is a model property (unit_price × quantity) and is also stored
    as a DB column so the invoice total can be aggregated with SUM(line_total)
    without loading all items into memory.

    Relationships
    -------------
    → Invoice (CASCADE delete) : parent invoice.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
        db_index=True,
    )

    description = models.CharField(max_length=255)
    item_type   = models.CharField(
        max_length=30, choices=ItemType.choices, default=ItemType.OTHER,
    )
    unit_price  = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantity    = models.PositiveSmallIntegerField(default=1)
    line_total  = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Stored as unit_price × quantity; updated on every save.",
    )

    # Optional reference back to the source record (drug, procedure, lab, etc.)
    reference_id = models.UUIDField(
        null=True, blank=True,
        help_text="Optional FK to source record (drug, procedure). Not enforced at DB level.",
    )

    class Meta:
        db_table            = "billing_invoiceitem"
        verbose_name        = "Invoice Item"
        verbose_name_plural = "Invoice Items"
        ordering            = ["item_type", "description"]
        indexes = [
            models.Index(fields=["invoice"], name="idx_invitem_invoice"),
        ]

    def __str__(self):
        return f"{self.description} × {self.quantity} @ {self.unit_price}"

    # ------------------------------------------------------------------
    # Save — compute line_total and cascade to parent invoice
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        # Guard: items cannot be added/changed on a non-draft invoice
        if self.invoice_id:
            invoice = Invoice.objects.get(pk=self.invoice_id)
            if not invoice.is_editable:
                raise ValidationError(
                    f"Cannot modify items on a '{invoice.status}' invoice. "
                    f"Only draft invoices are editable."
                )

        # Recompute line total
        self.line_total = (self.unit_price * self.quantity).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

        # Cascade total recomputation to parent invoice
        Invoice.objects.get(pk=self.invoice_id).save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

    def delete(self, *args, **kwargs):
        invoice_pk = self.invoice_id
        super().delete(*args, **kwargs)
        # Recalculate after deletion too
        try:
            Invoice.objects.get(pk=invoice_pk).save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])
        except Invoice.DoesNotExist:
            pass
