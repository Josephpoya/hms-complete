"""
accounts/serializers.py
=======================
Auth and user management serializers.

Security notes
--------------
- Password is always write_only. It never appears in any response.
- mfa_secret is excluded from all read serializers.
- failed_login_count and locked_until are admin-read-only; hidden from
  non-admin responses.
- Role changes are only allowed by admin users (enforced in the view,
  but the serializer validates the value set is legal).
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Role

User = get_user_model()


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends SimpleJWT's default serializer to:
      1. Inject role + email into the JWT access token payload.
      2. Enforce account lockout before issuing tokens.
      3. Increment failed_login_count on bad credentials.
      4. Reset failed_login_count on success.
    """

    def validate(self, attrs):
        email = attrs.get(self.username_field, "").lower()

        # Pre-auth lockout check (returns a clear message instead of generic 401)
        try:
            user = User.objects.get(email=email)
            if user.is_account_locked():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Account is temporarily locked due to too many failed login attempts. "
                            "Please wait 30 minutes or contact the administrator."
                        ]
                    }
                )
        except User.DoesNotExist:
            pass  # super() will handle invalid credentials uniformly

        try:
            data = super().validate(attrs)
        except Exception:
            # Increment counter on any auth failure
            try:
                bad_user = User.objects.get(email=email)
                bad_user.increment_failed_login()
            except User.DoesNotExist:
                pass
            raise

        # Success — clear lockout state
        self.user.reset_failed_login()
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Extra claims embedded in the JWT payload (readable client-side without a DB query)
        token["email"] = user.email
        token["role"]  = user.role
        token["mfa"]   = user.mfa_enabled
        return token


# ---------------------------------------------------------------------------
# User serializers
# ---------------------------------------------------------------------------

class UserPublicSerializer(serializers.ModelSerializer):
    """
    Safe read-only representation — used in nested contexts (appointment.created_by etc.).
    Exposes only non-sensitive identity fields.
    """
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model  = User
        fields = ("id", "email", "role", "role_display")
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """
    Full user representation for the /auth/me/ and admin /auth/users/ endpoints.
    Sensitive security fields (mfa_secret, failed_login_count, locked_until) are
    excluded — available via UserAdminSerializer to admins only.
    """
    role_display    = serializers.CharField(source="get_role_display", read_only=True)
    is_locked       = serializers.SerializerMethodField()
    doctor_profile  = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = (
            "id",
            "email",
            "role",
            "role_display",
            "is_active",
            "mfa_enabled",
            "is_locked",
            "doctor_profile",
            "created_at",
            "last_login",
            "updated_at",
        )
        read_only_fields = (
            "id", "role_display", "is_locked",
            "doctor_profile", "created_at", "last_login", "updated_at",
        )

    def get_is_locked(self, obj):
        return obj.is_account_locked()

    def get_doctor_profile(self, obj):
        """Return minimal doctor profile id if this user is a doctor."""
        if obj.is_doctor and hasattr(obj, "doctor_profile"):
            return str(obj.doctor_profile.id)
        return None

    def validate_role(self, value):
        request = self.context.get("request")
        # Only admins may change roles
        if self.instance and self.instance.role != value:
            if not (request and request.user.is_admin):
                raise serializers.ValidationError("Only administrators can change user roles.")
        return value


class UserAdminSerializer(UserSerializer):
    """
    Extended user serializer for admin-only views.
    Includes lockout state details.
    """
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + (
            "is_staff",
            "failed_login_count",
            "locked_until",
        )
        read_only_fields = UserSerializer.Meta.read_only_fields + (
            "failed_login_count",
            "locked_until",
        )


class RegisterUserSerializer(serializers.ModelSerializer):
    """
    Admin-only: create a new HMS user account.
    Password is validated against Django's full password validator chain.
    """
    password  = serializers.CharField(
        write_only=True,
        min_length=12,
        style={"input_type": "password"},
        help_text="Minimum 12 characters; must pass Django's password validators.",
    )
    password2 = serializers.CharField(
        write_only=True,
        label="Confirm password",
        style={"input_type": "password"},
    )

    class Meta:
        model  = User
        fields = ("email", "password", "password2", "role")

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        # Run Django's built-in password validators (min length, commonness, etc.)
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        return User.objects.create_user(**validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    """
    PATCH /auth/me/password/
    Allows a user to change their own password.
    """
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password     = serializers.CharField(write_only=True, min_length=12, style={"input_type": "password"})
    new_password2    = serializers.CharField(write_only=True, label="Confirm new password", style={"input_type": "password"})

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "New passwords do not match."})
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "New password must differ from the current password."}
            )
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class MFASetupSerializer(serializers.Serializer):
    """
    POST /auth/mfa/setup/   — returns the TOTP secret for QR code display.
    POST /auth/mfa/verify/  — verifies the TOTP code and enables MFA.
    """
    token = serializers.CharField(
        max_length=6, min_length=6,
        help_text="6-digit TOTP code from the authenticator app.",
    )


class UnlockUserSerializer(serializers.Serializer):
    """Admin-only: manually unlock a locked account."""
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
