"""
pharmacy/models.py
==================
Drug catalogue, inventory management, and prescription workflow.

Design decisions:
  - Drug.dispense() uses an F() expression for atomic stock deduction —
    prevents race conditions when two nurses dispense the same drug concurrently.
  - Prescription has its own status machine (pending → dispensed/cancelled/expired).
  - Controlled drugs flag — triggers extra audit steps (handled by the view).
  - requires_prescription flag — OTC drugs can be dispensed without a prescription.
  - Expiry date indexed — a weekly Celery task queries WHERE expiry_date <= now()+30d.
"""

import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.utils import timezone
from decimal import Decimal


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class DrugCategory(models.TextChoices):
    ANTIBIOTIC       = "antibiotic",       "Antibiotic"
    ANALGESIC        = "analgesic",        "Analgesic / Pain Relief"
    ANTIHYPERTENSIVE = "antihypertensive", "Antihypertensive"
    ANTIDIABETIC     = "antidiabetic",     "Antidiabetic"
    ANTIPARASITIC    = "antiparasitic",    "Antiparasitic / Antimalarial"
    ANTIFUNGAL       = "antifungal",       "Antifungal"
    ANTIRETROVIRAL   = "antiretroviral",   "Antiretroviral (ARV)"
    VITAMIN          = "vitamin",          "Vitamin / Supplement"
    VACCINE          = "vaccine",          "Vaccine"
    ANAESTHETIC      = "anaesthetic",      "Anaesthetic"
    CARDIOVASCULAR   = "cardiovascular",   "Cardiovascular"
    GASTROINTESTINAL = "gastrointestinal", "Gastrointestinal"
    RESPIRATORY      = "respiratory",      "Respiratory"
    HORMONAL         = "hormonal",         "Hormonal / Contraceptive"
    DERMATOLOGICAL   = "dermatological",   "Dermatological"
    OTHER            = "other",            "Other"


class DrugUnit(models.TextChoices):
    TABLET  = "tablet",  "Tablet"
    CAPSULE = "capsule", "Capsule"
    ML      = "ml",      "ml (liquid)"
    MG      = "mg",      "mg (injectable)"
    VIAL    = "vial",    "Vial"
    SACHET  = "sachet",  "Sachet"
    TUBE    = "tube",    "Tube"
    PATCH   = "patch",   "Patch"
    INHALER = "inhaler", "Inhaler"
    SUPPOSITORY = "suppository", "Suppository"


class PrescriptionStatus(models.TextChoices):
    PENDING   = "pending",   "Pending"
    DISPENSED = "dispensed", "Dispensed"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED   = "expired",   "Expired"


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class DrugManager(models.Manager):
    def active(self):
        return self.get_queryset().filter(is_active=True)

    def low_stock(self):
        """Drugs where stock <= reorder_level."""
        return self.active().filter(stock_quantity__lte=F("reorder_level"))

    def expiring_soon(self, days=30):
        from datetime import timedelta
        cutoff = date.today() + timedelta(days=days)
        return self.active().filter(expiry_date__lte=cutoff, expiry_date__gte=date.today())

    def controlled(self):
        return self.active().filter(controlled_drug=True)


# ---------------------------------------------------------------------------
# Drug
# ---------------------------------------------------------------------------

class Drug(models.Model):
    """
    Drug catalogue entry — master record for every stocked medication.

    Relationships
    -------------
    ← pharmacy.Prescription : all prescriptions for this drug.

    Inventory notes
    ---------------
    stock_quantity is updated atomically via Drug.dispense() using an F()
    expression. Never update it directly (e.g. drug.stock_quantity -= 5)
    as that creates a read-modify-write race condition under concurrency.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ---- Identity ---------------------------------------------------------
    name         = models.CharField(max_length=200, db_index=True, help_text="Brand name.")
    generic_name = models.CharField(max_length=200, db_index=True, help_text="INN / generic name.")
    category     = models.CharField(max_length=40, choices=DrugCategory.choices, db_index=True)
    unit         = models.CharField(max_length=20, choices=DrugUnit.choices)
    strength     = models.CharField(
        max_length=50, blank=True,
        help_text="e.g. 500mg, 250mg/5ml.",
    )
    description  = models.TextField(blank=True)

    # ---- Inventory --------------------------------------------------------
    stock_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Current stock. Updated atomically by dispense().",
    )
    reorder_level = models.PositiveIntegerField(
        default=50,
        help_text="Low-stock alert fires when stock_quantity <= this value.",
    )
    unit_price    = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Cost per unit in the hospital's default currency.",
    )

    # ---- Regulatory -------------------------------------------------------
    barcode               = models.CharField(max_length=60, unique=True, blank=True, null=True)
    requires_prescription = models.BooleanField(
        default=True,
        help_text="OTC drugs (False) can be dispensed without a prescription.",
    )
    controlled_drug       = models.BooleanField(
        default=False,
        help_text="Schedule I–V controlled substance — requires extra audit steps.",
    )

    # ---- Shelf life -------------------------------------------------------
    expiry_date  = models.DateField(null=True, blank=True, db_index=True)
    batch_number = models.CharField(max_length=60, blank=True)

    # ---- Supplier ---------------------------------------------------------
    manufacturer = models.CharField(max_length=150, blank=True)
    supplier     = models.CharField(max_length=150, blank=True)

    # ---- Status -----------------------------------------------------------
    is_active  = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DrugManager()

    class Meta:
        db_table            = "pharmacy_drug"
        verbose_name        = "Drug"
        verbose_name_plural = "Drugs"
        ordering            = ["generic_name", "name"]
        indexes = [
            models.Index(fields=["category", "is_active"],  name="idx_drug_cat_active"),
            models.Index(fields=["expiry_date"],             name="idx_drug_expiry"),
            models.Index(fields=["stock_quantity"],          name="idx_drug_stock"),
        ]

    def __str__(self):
        parts = [self.name]
        if self.strength:
            parts.append(self.strength)
        parts.append(f"({self.generic_name})")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.reorder_level

    @property
    def is_out_of_stock(self):
        return self.stock_quantity == 0

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < date.today())

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    # ------------------------------------------------------------------
    # Inventory methods
    # ------------------------------------------------------------------

    def dispense(self, quantity):
        """
        Atomically deduct `quantity` units from stock.

        Uses a DB-level UPDATE with F() expression — safe under concurrency.
        A SELECT FOR UPDATE could also be used but F() is lighter.
        Raises ValueError if insufficient stock or drug is expired.
        """
        if quantity <= 0:
            raise ValueError("Quantity to dispense must be a positive integer.")
        if self.is_expired:
            raise ValueError(f"Cannot dispense expired drug: {self.name} (expired {self.expiry_date}).")
        if self.is_out_of_stock or self.stock_quantity < quantity:
            raise ValueError(
                f"Insufficient stock for '{self.name}'. "
                f"Available: {self.stock_quantity}, requested: {quantity}."
            )
        Drug.objects.filter(pk=self.pk).update(
            stock_quantity=F("stock_quantity") - quantity
        )
        self.refresh_from_db(fields=["stock_quantity"])

    def restock(self, quantity, batch_number=None, expiry_date=None):
        """
        Add stock — called when a purchase order is received.
        Updates batch_number and expiry_date if provided.
        """
        if quantity <= 0:
            raise ValueError("Restock quantity must be positive.")
        update_kwargs = {"stock_quantity": F("stock_quantity") + quantity}
        if batch_number:
            update_kwargs["batch_number"] = batch_number
        if expiry_date:
            update_kwargs["expiry_date"] = expiry_date
        Drug.objects.filter(pk=self.pk).update(**update_kwargs)
        self.refresh_from_db()


# ---------------------------------------------------------------------------
# Prescription
# ---------------------------------------------------------------------------

class Prescription(models.Model):
    """
    A doctor's prescription for a specific drug for a specific patient.

    Lifecycle
    ---------
    pending   → dispensed   (nurse/admin calls dispense())
    pending   → cancelled   (doctor or admin cancels before dispensing)
    pending   → expired     (Celery task expires unfilled prescriptions after N days)

    Relationships
    -------------
    → patients.Patient              : the prescribed patient.
    → doctors.Doctor                : the prescribing doctor.
    → records.MedicalRecord         : the EHR record this prescription is linked to.
    → pharmacy.Drug                 : the prescribed drug.
    → accounts.User (dispensed_by)  : the nurse/admin who dispensed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="prescriptions",
        db_index=True,
    )
    doctor = models.ForeignKey(
        "doctors.Doctor",
        on_delete=models.PROTECT,
        related_name="prescriptions",
        db_index=True,
    )
    medical_record = models.ForeignKey(
        "records.MedicalRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions",
        help_text="EHR note this prescription was written in.",
    )
    drug = models.ForeignKey(
        Drug,
        on_delete=models.PROTECT,
        related_name="prescriptions",
        db_index=True,
        help_text="PROTECT — historical prescriptions must not break if drug is deactivated.",
    )

    # ---- Dosage instructions ----------------------------------------------
    dosage              = models.CharField(max_length=100, help_text="e.g. 500mg.")
    frequency           = models.CharField(max_length=60,  help_text="e.g. twice daily, every 8 hours.")
    duration_days       = models.PositiveSmallIntegerField(help_text="Number of days to take the medication.")
    quantity_prescribed = models.PositiveSmallIntegerField(help_text="Total units to dispense.")
    instructions        = models.TextField(
        blank=True,
        help_text="Patient instructions: take with food, avoid alcohol, refrigerate, etc.",
    )
    route               = models.CharField(
        max_length=30, blank=True,
        help_text="Route of administration: oral, IV, IM, topical, etc.",
    )

    # ---- Status -----------------------------------------------------------
    status = models.CharField(
        max_length=20,
        choices=PrescriptionStatus.choices,
        default=PrescriptionStatus.PENDING,
        db_index=True,
    )

    # ---- Timestamps -------------------------------------------------------
    prescribed_at = models.DateTimeField(default=timezone.now)
    dispensed_at  = models.DateTimeField(null=True, blank=True)
    dispensed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dispensed_prescriptions",
        help_text="Nurse or admin who dispensed the medication.",
    )
    expiry_date   = models.DateField(
        null=True, blank=True,
        help_text="Date after which this prescription can no longer be filled.",
    )

    class Meta:
        db_table            = "pharmacy_prescription"
        verbose_name        = "Prescription"
        verbose_name_plural = "Prescriptions"
        ordering            = ["-prescribed_at"]
        indexes = [
            models.Index(fields=["patient", "status"],   name="idx_rx_patient_status"),
            models.Index(fields=["doctor", "prescribed_at"], name="idx_rx_doctor_ts"),
            models.Index(fields=["drug", "status"],      name="idx_rx_drug_status"),
        ]

    def __str__(self):
        return (
            f"{self.drug.name} {self.dosage} for {self.patient} "
            f"by {self.doctor} [{self.get_status_display()}]"
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_pending(self):
        return self.status == PrescriptionStatus.PENDING

    @property
    def is_dispensed(self):
        return self.status == PrescriptionStatus.DISPENSED

    @property
    def is_prescription_expired(self):
        return bool(self.expiry_date and self.expiry_date < date.today())

    # ------------------------------------------------------------------
    # Business methods
    # ------------------------------------------------------------------

    def dispense(self, dispensed_by_user):
        """
        Dispense the prescription:
          1. Validate status and expiry.
          2. Atomically deduct stock from the drug.
          3. Update prescription status.

        Raises ValueError on any failure — caller should wrap in a transaction.
        """
        if self.status != PrescriptionStatus.PENDING:
            raise ValueError(
                f"Cannot dispense — prescription status is '{self.status}'."
            )
        if self.is_prescription_expired:
            raise ValueError(
                f"This prescription expired on {self.expiry_date}. "
                f"A new prescription is required."
            )

        # Atomic stock deduction (raises ValueError if insufficient)
        self.drug.dispense(self.quantity_prescribed)

        self.status       = PrescriptionStatus.DISPENSED
        self.dispensed_at = timezone.now()
        self.dispensed_by = dispensed_by_user
        self.save(update_fields=["status", "dispensed_at", "dispensed_by"])

    def cancel(self, reason=""):
        if self.status != PrescriptionStatus.PENDING:
            raise ValueError(
                f"Cannot cancel — prescription is already '{self.status}'."
            )
        self.status = PrescriptionStatus.CANCELLED
        if reason:
            self.instructions = f"[CANCELLED: {reason}] {self.instructions}".strip()
        self.save(update_fields=["status", "instructions"])

    def expire(self):
        """Called by the Celery expiry task."""
        if self.status == PrescriptionStatus.PENDING:
            self.status = PrescriptionStatus.EXPIRED
            self.save(update_fields=["status"])
