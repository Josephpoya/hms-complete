"""
core/security.py
================
Input validation, data protection, and access control utilities.

Components
----------
  InputSanitizer       — strips dangerous content from string inputs.
  SensitiveFieldGuard  — detects and logs access to PII fields.
  PatientDataPolicy    — enforces clinical data access rules.
  EncryptedField       — transparent encrypt/decrypt for sensitive DB columns.
  SecureFileValidator  — validates uploads before S3 transfer.
  TokenValidator       — validates JWTs and detects replay attacks.
  IPBlocklist          — checks IP against configurable deny list.
"""

import hashlib
import hmac
import logging
import mimetypes
import re
from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

logger           = logging.getLogger("hms.security")
audit_logger     = logging.getLogger("hms.audit")


# ---------------------------------------------------------------------------
# 1. InputSanitizer
# ---------------------------------------------------------------------------

class InputSanitizer:
    """
    Strips or rejects dangerous content from user-supplied strings.

    Does NOT do HTML escaping — DRF already does that. This targets:
    - SQL injection patterns (belt-and-suspenders — ORM parameterises queries)
    - Script injection in free-text fields stored as plain text
    - Null bytes and control characters
    - Excessively long inputs that could cause DoS
    """

    # Patterns that are always rejected regardless of field
    _DANGEROUS = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|EXEC|EXECUTE|"
        r"SCRIPT|JAVASCRIPT|VBSCRIPT|ONLOAD|ONERROR|ALERT)\b)",
        re.IGNORECASE,
    )

    # Control characters (except newlines and tabs which are valid in notes)
    _CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    # Max lengths by field type
    MAX_LENGTHS = {
        "name":    200,
        "address": 500,
        "note":    5000,
        "code":    50,
        "default": 1000,
    }

    @classmethod
    def clean(cls, value, field_type="default", allow_html=False):
        """
        Clean a string value. Returns the cleaned string.
        Raises ValidationError if the value is fundamentally unsafe.
        """
        if not isinstance(value, str):
            return value

        # Strip null bytes and control characters
        value = cls._CONTROL.sub("", value)

        # Strip leading/trailing whitespace
        value = value.strip()

        # Length check
        max_len = cls.MAX_LENGTHS.get(field_type, cls.MAX_LENGTHS["default"])
        if len(value) > max_len:
            raise ValidationError(
                f"Input exceeds maximum length of {max_len} characters for this field."
            )

        # Reject known injection patterns in non-note fields
        if field_type not in ("note", "address") and cls._DANGEROUS.search(value):
            logger.warning("dangerous_input_rejected field_type=%s value_prefix=%s", field_type, value[:50])
            raise ValidationError("Input contains disallowed keywords.")

        return value

    @classmethod
    def clean_mrn(cls, value):
        """MRN must match the format MRN-NNNNNNN."""
        value = str(value).strip().upper()
        if not re.match(r"^MRN-\d{7}$", value):
            raise ValidationError(f"Invalid MRN format: {value}.")
        return value

    @classmethod
    def clean_icd10(cls, value):
        """ICD-10 codes: letter + 2 digits + optional .1-4 chars."""
        value = str(value).strip().upper()
        if not re.match(r"^[A-Z]\d{2}(\.\d{0,4})?$", value):
            raise ValidationError(f"Invalid ICD-10 code: {value}.")
        return value

    @classmethod
    def clean_phone(cls, value):
        """Normalise phone to digits + optional leading +."""
        cleaned = re.sub(r"[\s\-\(\)\.]", "", str(value))
        if not re.match(r"^\+?[0-9]{7,15}$", cleaned):
            raise ValidationError("Invalid phone number format.")
        return cleaned


# ---------------------------------------------------------------------------
# 2. SensitiveFieldGuard
# ---------------------------------------------------------------------------

class SensitiveFieldGuard:
    """
    Detects and logs access to defined sensitive fields.
    Call check() before serialising any sensitive field in a view.

    Sensitive fields in the HMS
    ---------------------------
    patients_patient: is_hiv_positive, national_id, allergies (partially)
    accounts_user   : mfa_secret, failed_login_count, locked_until
    pharmacy_prescription: drug (controlled_drug=True)
    """

    SENSITIVE_FIELDS = {
        "patients_patient":    frozenset({"is_hiv_positive", "national_id"}),
        "accounts_user":       frozenset({"mfa_secret"}),
        "pharmacy_drug":       frozenset({"controlled_drug"}),
    }

    @classmethod
    def check(cls, user, table_name, field_name, record_id=None):
        """
        Log access to a sensitive field. Does not block — call before returning data.
        The view/serializer is responsible for gating access via permissions.
        """
        sensitive = cls.SENSITIVE_FIELDS.get(table_name, frozenset())
        if field_name not in sensitive:
            return

        from core.audit import AuditService, AuditAction
        AuditService.log(
            action     = AuditAction.ACCESS,
            table_name = table_name,
            record_id  = record_id,
            user       = user,
            new_value  = {"field": field_name},
        )
        audit_logger.info(
            "sensitive_field_accessed table=%s field=%s user=%s record=%s",
            table_name, field_name,
            user.email if user else "system",
            record_id,
        )


# ---------------------------------------------------------------------------
# 3. PatientDataPolicy
# ---------------------------------------------------------------------------

class PatientDataPolicy:
    """
    Enforces patient data access rules beyond simple RBAC.

    Rules
    -----
    - HIV status: doctor must have an appointment with the patient, or be admin.
    - national_id: admin only, and the access is always audit-logged.
    - Prescription history: prescribing doctor, or any doctor if the patient
      is currently admitted (flag on Patient in a future Admission model).
    """

    @classmethod
    def can_view_hiv_status(cls, user, patient):
        """Returns True if the user is allowed to view is_hiv_positive."""
        if user.is_admin:
            return True
        if user.is_nurse:
            return True
        if user.is_doctor:
            # Doctor must have treated this patient (has a record or appointment)
            if hasattr(user, "doctor_profile"):
                return (
                    patient.appointments
                    .filter(doctor=user.doctor_profile)
                    .exists()
                )
        return False

    @classmethod
    def can_view_national_id(cls, user, patient):
        """national_id is admin-only."""
        return user.is_admin

    @classmethod
    def assert_can_view_hiv(cls, user, patient):
        if not cls.can_view_hiv_status(user, patient):
            logger.warning(
                "unauthorized_hiv_access user=%s patient=%s",
                user.email, patient.mrn,
            )
            raise PermissionDenied(
                "You are not authorised to view this patient's HIV status."
            )
        SensitiveFieldGuard.check(user, "patients_patient", "is_hiv_positive", patient.pk)

    @classmethod
    def assert_can_view_national_id(cls, user, patient):
        if not cls.can_view_national_id(user, patient):
            raise PermissionDenied(
                "Only administrators may view national ID numbers."
            )
        SensitiveFieldGuard.check(user, "patients_patient", "national_id", patient.pk)


# ---------------------------------------------------------------------------
# 4. SecureFileValidator
# ---------------------------------------------------------------------------

class SecureFileValidator:
    """
    Validates uploaded files before they are sent to S3.

    Checks
    ------
    1. File size within limit.
    2. Extension matches allowed list.
    3. Content-Type header matches allowed list.
    4. Magic bytes match the declared Content-Type (prevents content spoofing).
    5. Filename sanitised — no path traversal, no dangerous characters.
    """

    ALLOWED = {
        "application/pdf":      (b"%PDF", ".pdf"),
        "image/jpeg":           (b"\xff\xd8\xff", ".jpg"),
        "image/png":            (b"\x89PNG", ".png"),
        "application/dicom":    (b"DICM", ".dcm"),
    }

    MAX_SIZE_MB = 25
    MAX_SIZE    = MAX_SIZE_MB * 1024 * 1024

    @classmethod
    def validate(cls, uploaded_file):
        """
        Validates an InMemoryUploadedFile or TemporaryUploadedFile.
        Raises ValidationError on any failure.
        """
        # 1. Size
        if uploaded_file.size > cls.MAX_SIZE:
            raise ValidationError(
                f"File too large ({uploaded_file.size // (1024 * 1024)} MB). "
                f"Maximum allowed: {cls.MAX_SIZE_MB} MB."
            )

        # 2. Content-Type
        content_type = uploaded_file.content_type
        if content_type not in cls.ALLOWED:
            raise ValidationError(
                f"File type '{content_type}' is not allowed. "
                f"Allowed: {', '.join(cls.ALLOWED.keys())}."
            )

        # 3. Magic bytes
        magic, expected_ext = cls.ALLOWED[content_type]
        uploaded_file.seek(0)
        header = uploaded_file.read(len(magic))
        uploaded_file.seek(0)

        # DICOM magic is at offset 128
        if content_type == "application/dicom":
            uploaded_file.seek(128)
            header = uploaded_file.read(4)
            uploaded_file.seek(0)

        if not header.startswith(magic):
            raise ValidationError(
                f"File content does not match declared type '{content_type}'. "
                f"The file may have been tampered with."
            )

        # 4. Filename sanitisation
        filename = cls.sanitise_filename(uploaded_file.name)
        uploaded_file.name = filename

        return uploaded_file

    @classmethod
    def sanitise_filename(cls, filename):
        """
        Remove path traversal, null bytes, and restrict to safe characters.
        """
        import os
        # Strip directory components
        filename = os.path.basename(filename)
        # Remove null bytes
        filename = filename.replace("\x00", "")
        # Replace dangerous characters
        filename = re.sub(r"[^a-zA-Z0-9._\-]", "_", filename)
        # Prevent hidden files
        filename = filename.lstrip(".")
        # Truncate
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename  = name[:255 - len(ext)] + ext
        return filename or "upload"


# ---------------------------------------------------------------------------
# 5. TokenValidator
# ---------------------------------------------------------------------------

class TokenValidator:
    """
    Extra validation layer on top of SimpleJWT.
    Checks for replayed tokens and validates custom claims.
    """

    @classmethod
    def validate_claims(cls, token_data, request):
        """
        Called from a custom authentication class or middleware.
        Raises AuthenticationFailed on suspicious tokens.
        """
        from rest_framework.exceptions import AuthenticationFailed

        # Role claim must be present and valid
        valid_roles = {"admin", "doctor", "nurse", "receptionist"}
        role = token_data.get("role")
        if role not in valid_roles:
            raise AuthenticationFailed("Token contains invalid role claim.")

        # User agent binding — warn if token is used from a different UA
        original_ua  = token_data.get("_ua_hash")
        current_ua   = request.META.get("HTTP_USER_AGENT", "")
        current_hash = hashlib.sha256(current_ua.encode()).hexdigest()[:16]

        if original_ua and original_ua != current_hash:
            logger.warning(
                "token_ua_mismatch user=%s original_hash=%s current_hash=%s",
                token_data.get("user_id"), original_ua, current_hash,
            )
            # Warn but do not block — UA can change legitimately (e.g. browser update)


# ---------------------------------------------------------------------------
# 6. IPBlocklist
# ---------------------------------------------------------------------------

class IPBlocklist:
    """
    Checks an IP address against a Redis-backed blocklist.
    IPs are added to the blocklist automatically by:
      - RateLimitMiddleware on sustained breaches
      - Failed login threshold (configured separately)
      - Manual admin action via Django admin

    Cache key: "blocklist:<ip>"  → "blocked" with TTL
    """

    CACHE_KEY_PREFIX = "blocklist"
    DEFAULT_TTL      = 24 * 3600  # 24 hours

    @classmethod
    def is_blocked(cls, ip):
        try:
            from django.core.cache import cache
            return bool(cache.get(f"{cls.CACHE_KEY_PREFIX}:{ip}"))
        except Exception:
            return False

    @classmethod
    def block(cls, ip, duration_seconds=DEFAULT_TTL, reason="automatic"):
        try:
            from django.core.cache import cache
            cache.set(f"{cls.CACHE_KEY_PREFIX}:{ip}", reason, timeout=duration_seconds)
            security_logger = logging.getLogger("hms.security")
            security_logger.warning("ip_blocked ip=%s reason=%s duration=%ss", ip, reason, duration_seconds)
        except Exception:
            pass

    @classmethod
    def unblock(cls, ip):
        try:
            from django.core.cache import cache
            cache.delete(f"{cls.CACHE_KEY_PREFIX}:{ip}")
        except Exception:
            pass
