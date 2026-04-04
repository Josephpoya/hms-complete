"""
core/validators.py
==================
Reusable Django/DRF validators that can be attached to model fields
or used standalone in serializers.

All validators raise django.core.exceptions.ValidationError
(which DRF's serializer framework translates to its own ValidationError).
"""

import re
from datetime import date

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


@deconstructible
class PhoneValidator:
    """
    Validates E.164-compatible phone numbers.
    Accepts: +256700000000, 0700000000, +1-800-555-0100 (hyphens stripped).
    """
    message = "Enter a valid phone number (7–15 digits, optional + prefix)."
    code    = "invalid_phone"

    def __call__(self, value):
        cleaned = re.sub(r"[\s\-\(\)\.]", "", str(value))
        if not re.match(r"^\+?[0-9]{7,15}$", cleaned):
            raise ValidationError(self.message, code=self.code)


@deconstructible
class MRNValidator:
    """Validates Medical Record Number format: MRN-NNNNNNN."""
    message = "MRN must match format MRN-NNNNNNN (e.g. MRN-0001234)."
    code    = "invalid_mrn"

    def __call__(self, value):
        if not re.match(r"^MRN-\d{7}$", str(value).upper()):
            raise ValidationError(self.message, code=self.code)


@deconstructible
class ICD10Validator:
    """Validates ICD-10 code format: letter + 2 digits + optional .1-4 chars."""
    message = "Enter a valid ICD-10 code (e.g. J06.9, A09, K21.0)."
    code    = "invalid_icd10"

    def __call__(self, value):
        if not re.match(r"^[A-Z]\d{2}(\.\d{0,4})?$", str(value).upper()):
            raise ValidationError(self.message, code=self.code)


@deconstructible
class FutureDateValidator:
    """Validates that a date is in the future."""
    message = "Date must be in the future."
    code    = "date_not_future"

    def __call__(self, value):
        if isinstance(value, date) and value <= date.today():
            raise ValidationError(self.message, code=self.code)


@deconstructible
class PastDateValidator:
    """Validates that a date is in the past."""
    message = "Date must be in the past."
    code    = "date_not_past"

    def __call__(self, value):
        if isinstance(value, date) and value >= date.today():
            raise ValidationError(self.message, code=self.code)


@deconstructible
class PositiveDecimalValidator:
    """Validates that a Decimal value is >= 0."""
    message = "Value must be zero or positive."
    code    = "negative_decimal"

    def __call__(self, value):
        if value is not None and value < 0:
            raise ValidationError(self.message, code=self.code)


@deconstructible
class NoSQLInjectionValidator:
    """
    Belt-and-suspenders guard against SQL injection in free-text fields.
    The ORM parameterises all queries, so this is advisory — it catches
    obviously malicious input early and logs it.
    """
    _PATTERN = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|EXEC|EXECUTE)\b)",
        re.IGNORECASE,
    )
    message = "Input contains disallowed keywords."
    code    = "potential_injection"

    def __call__(self, value):
        if isinstance(value, str) and self._PATTERN.search(value):
            import logging
            logging.getLogger("hms.security").warning(
                "sql_injection_pattern_detected value_prefix=%s", value[:50]
            )
            raise ValidationError(self.message, code=self.code)


@deconstructible
class SafeFilenameValidator:
    """
    Validates upload filenames — no path traversal, no null bytes,
    only safe characters.
    """
    message = "Filename contains invalid characters."
    code    = "invalid_filename"
    _SAFE   = re.compile(r"^[a-zA-Z0-9._\-]+$")

    def __call__(self, value):
        import os
        basename = os.path.basename(str(value))
        if not self._SAFE.match(basename):
            raise ValidationError(self.message, code=self.code)
        if basename.startswith("."):
            raise ValidationError("Filenames cannot start with a dot.", code=self.code)


# ---------------------------------------------------------------------------
# Composite validator used in serializers
# ---------------------------------------------------------------------------

def validate_vitals_dict(value):
    """
    Standalone validator for the vitals JSONB field.
    Can be used in serializer.validate_vitals() or as a model field validator.
    """
    if value is None:
        return value

    ALLOWED_KEYS = {
        "bp_systolic", "bp_diastolic", "pulse", "temperature",
        "spo2", "respiratory_rate", "weight_kg", "height_cm",
        "bmi", "blood_glucose", "urine_output",
    }
    RANGES = {
        "bp_systolic":      (40, 300),
        "bp_diastolic":     (20, 200),
        "pulse":            (20, 300),
        "temperature":      (30, 45),
        "spo2":             (50, 100),
        "respiratory_rate": (5, 60),
        "weight_kg":        (0.5, 500),
        "height_cm":        (20, 300),
        "bmi":              (5, 100),
        "blood_glucose":    (0, 100),
        "urine_output":     (0, 100_000),
    }

    if not isinstance(value, dict):
        raise ValidationError("Vitals must be a JSON object.")

    unknown = set(value.keys()) - ALLOWED_KEYS
    if unknown:
        raise ValidationError(f"Unknown vital sign keys: {unknown}.")

    errors = []
    for key, val in value.items():
        if val is None:
            continue
        lo, hi = RANGES.get(key, (None, None))
        if lo is not None:
            try:
                num = float(val)
                if not (lo <= num <= hi):
                    errors.append(f"{key}: value {val} is outside valid range [{lo}, {hi}].")
            except (TypeError, ValueError):
                errors.append(f"{key}: must be a number.")

    if errors:
        raise ValidationError(errors)

    return value
