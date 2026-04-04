"""
accounts/models.py
==================
Custom User model replacing Django's built-in User entirely.

Design decisions:
  - UUID primary key: no sequential IDs leak record counts via URLs.
  - Email is the login identifier (no username field).
  - Single `role` field per user; fine-grained object-level permissions
    are enforced by DRF permission classes, not Django groups.
  - Argon2id password hashing (configured in settings.PASSWORD_HASHERS).
  - TOTP MFA fields: secret encrypted at rest in production
    (swap CharField -> EncryptedCharField from django-encrypted-fields).
  - Brute-force lockout enforced in the custom TokenObtainPairSerializer.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class Role(models.TextChoices):
    ADMIN        = "admin",        "Admin"
    DOCTOR       = "doctor",       "Doctor"
    NURSE        = "nurse",        "Nurse"
    RECEPTIONIST = "receptionist", "Receptionist"


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager):
    """Email-based manager; normalises to lowercase before saving."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)
        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)

    def active(self):
        return self.get_queryset().filter(is_active=True)

    def by_role(self, role):
        return self.get_queryset().filter(role=role, is_active=True)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin):
    """
    HMS system user — one account per staff member.

    Roles
    -----
    admin        : full system access, user management, audit logs.
    doctor       : EHR authoring, prescriptions, own appointments.
    nurse        : vitals, medication administration, ward patients.
    receptionist : patient registration, appointment booking, billing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(
        max_length=255, unique=True, db_index=True,
        help_text="Login identifier; stored lowercase.",
    )

    role = models.CharField(
        max_length=30, choices=Role.choices, db_index=True,
        help_text="Determines RBAC access across all HMS modules.",
    )

    # Django auth flags
    is_active = models.BooleanField(
        default=True,
        help_text="Deactivate instead of deleting — preserves audit history.",
    )
    is_staff = models.BooleanField(default=False, help_text="Django admin access.")

    # MFA (TOTP via e.g. Google Authenticator)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret  = models.CharField(
        max_length=64, blank=True, null=True,
        help_text="Base32 TOTP secret. Use EncryptedCharField in production.",
    )

    # Brute-force lockout
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(
        null=True, blank=True,
        help_text="Account refuses login until this UTC datetime.",
    )

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["role"]

    class Meta:
        db_table            = "accounts_user"
        verbose_name        = "User"
        verbose_name_plural = "Users"
        ordering            = ["email"]
        indexes = [
            models.Index(fields=["email"],             name="idx_user_email"),
            models.Index(fields=["role"],              name="idx_user_role"),
            models.Index(fields=["is_active", "role"], name="idx_user_active_role"),
        ]

    def __str__(self):
        return f"{self.email} [{self.get_role_display()}]"

    # ------------------------------------------------------------------
    # Role helpers — always use these, never compare .role directly
    # ------------------------------------------------------------------

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_doctor(self):
        return self.role == Role.DOCTOR

    @property
    def is_nurse(self):
        return self.role == Role.NURSE

    @property
    def is_receptionist(self):
        return self.role == Role.RECEPTIONIST

    @property
    def is_clinical_staff(self):
        """True for doctors and nurses."""
        return self.role in (Role.DOCTOR, Role.NURSE)

    # ------------------------------------------------------------------
    # Lockout helpers
    # ------------------------------------------------------------------

    def is_account_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def increment_failed_login(self):
        self.failed_login_count += 1
        max_attempts    = getattr(settings, "HMS_MAX_LOGIN_ATTEMPTS", 5)
        lockout_minutes = getattr(settings, "HMS_ACCOUNT_LOCKOUT_MINUTES", 30)
        if self.failed_login_count >= max_attempts:
            self.locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
        self.save(update_fields=["failed_login_count", "locked_until", "updated_at"])

    def reset_failed_login(self):
        if self.failed_login_count > 0 or self.locked_until:
            self.failed_login_count = 0
            self.locked_until       = None
            self.save(update_fields=["failed_login_count", "locked_until", "updated_at"])

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)
