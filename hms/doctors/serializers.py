"""
doctors/serializers.py
======================
Doctor and availability serializers.

  DoctorMinimalSerializer    — safe for nesting (name + specialisation).
  DoctorListSerializer       — directory listing.
  DoctorDetailSerializer     — full profile; write access admin-only.
  DoctorAvailabilitySerializer — weekly slot CRUD.
  DoctorWorkloadSerializer   — read-only today's stats for dashboards.

Validation
----------
- licence_number uniqueness (excluding current instance on update).
- licence_expiry must be a future date.
- consultation_fee >= 0.
- Availability: end_time > start_time; no duplicate weekday+time per doctor.
- max_patients_per_day: 1–100 range.
"""

from datetime import date

from rest_framework import serializers

from accounts.serializers import UserPublicSerializer
from .models import Doctor, DoctorAvailability, Department


# ---------------------------------------------------------------------------
# Minimal — safe for nesting
# ---------------------------------------------------------------------------

class DoctorMinimalSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model  = Doctor
        fields = ("id", "full_name", "specialisation", "department")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)
    duration_hours  = serializers.SerializerMethodField()

    class Meta:
        model  = DoctorAvailability
        fields = (
            "id",
            "weekday",
            "weekday_display",
            "start_time",
            "end_time",
            "duration_hours",
            "is_active",
        )
        read_only_fields = ("id", "weekday_display", "duration_hours")

    def get_duration_hours(self, obj):
        from datetime import datetime, timedelta
        start = datetime.combine(date.today(), obj.start_time)
        end   = datetime.combine(date.today(), obj.end_time)
        delta = end - start
        return round(delta.total_seconds() / 3600, 2)

    def validate(self, attrs):
        start = attrs.get("start_time") or (self.instance and self.instance.start_time)
        end   = attrs.get("end_time")   or (self.instance and self.instance.end_time)
        if start and end and start >= end:
            raise serializers.ValidationError(
                {"end_time": "End time must be after start time."}
            )
        return attrs

    def validate_weekday(self, value):
        if not (0 <= value <= 6):
            raise serializers.ValidationError("Weekday must be 0 (Monday) to 6 (Sunday).")
        return value

    def create(self, validated_data):
        doctor  = validated_data.get("doctor")
        weekday = validated_data.get("weekday")
        start   = validated_data.get("start_time")

        # Check for duplicate slot
        if DoctorAvailability.objects.filter(
            doctor=doctor, weekday=weekday, start_time=start
        ).exists():
            raise serializers.ValidationError(
                "An availability slot already exists for this doctor on this day and time."
            )
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class DoctorListSerializer(serializers.ModelSerializer):
    full_name             = serializers.ReadOnlyField()
    email                 = serializers.ReadOnlyField()
    todays_patient_count  = serializers.SerializerMethodField()

    class Meta:
        model  = Doctor
        fields = (
            "id",
            "full_name",
            "first_name",
            "last_name",
            "email",
            "specialisation",
            "department",
            "qualification",
            "consultation_fee",
            "is_available",
            "accepts_walk_in",
            "todays_patient_count",
        )
        read_only_fields = fields

    def get_todays_patient_count(self, obj):
        return obj.todays_appointment_count()


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

class DoctorDetailSerializer(serializers.ModelSerializer):
    """
    Full doctor profile.
    user field is read-only (set at creation and never changed).
    availability is a nested read-only list; managed via dedicated endpoint.
    """
    full_name        = serializers.ReadOnlyField()
    email            = serializers.ReadOnlyField()
    licence_is_valid       = serializers.ReadOnlyField()
    licence_expiring_soon  = serializers.ReadOnlyField()
    is_fully_booked_today  = serializers.SerializerMethodField()
    availability           = DoctorAvailabilitySerializer(many=True, read_only=True)
    user                   = UserPublicSerializer(read_only=True)
    # user_id accepted at creation only
    user_id                = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model  = Doctor
        fields = (
            "id",
            "user",
            "user_id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "photo_url",
            # Professional
            "specialisation",
            "qualification",
            "licence_number",
            "licence_expiry",
            "licence_is_valid",
            "licence_expiring_soon",
            "department",
            "years_experience",
            "bio",
            # Scheduling
            "consultation_fee",
            "max_patients_per_day",
            "is_available",
            "accepts_walk_in",
            "is_fully_booked_today",
            # Nested
            "availability",
            # Timestamps
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "full_name",
            "email",
            "licence_is_valid",
            "licence_expiring_soon",
            "is_fully_booked_today",
            "availability",
            "user",
            "created_at",
            "updated_at",
        )

    def get_is_fully_booked_today(self, obj):
        return obj.is_fully_booked_today()

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    def validate_licence_number(self, value):
        qs = Doctor.objects.filter(licence_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "This licence number is already registered to another doctor."
            )
        return value.strip().upper()

    def validate_licence_expiry(self, value):
        if value and value < date.today():
            raise serializers.ValidationError(
                "Licence expiry date is already in the past. "
                "The doctor cannot see patients with an expired licence."
            )
        return value

    def validate_consultation_fee(self, value):
        if value < 0:
            raise serializers.ValidationError("Consultation fee cannot be negative.")
        return value

    def validate_max_patients_per_day(self, value):
        if not (1 <= value <= 100):
            raise serializers.ValidationError("Max patients per day must be between 1 and 100.")
        return value

    def validate_user_id(self, value):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(pk=value, role="doctor")
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "No active user with role='doctor' found for this ID."
            )
        if hasattr(user, "doctor_profile"):
            raise serializers.ValidationError(
                "This user already has a doctor profile."
            )
        return value

    # ------------------------------------------------------------------
    # Create / update
    # ------------------------------------------------------------------

    def create(self, validated_data):
        user_id = validated_data.pop("user_id", None)
        if user_id:
            validated_data["user_id"] = user_id
        elif not validated_data.get("user_id"):
            raise serializers.ValidationError(
                {"user_id": "user_id is required when creating a doctor profile."}
            )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # user_id cannot be changed after creation
        validated_data.pop("user_id", None)
        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Workload dashboard
# ---------------------------------------------------------------------------

class DoctorWorkloadSerializer(serializers.ModelSerializer):
    """Read-only snapshot of a doctor's current day — for dashboard widgets."""
    full_name             = serializers.ReadOnlyField()
    todays_count          = serializers.SerializerMethodField()
    is_fully_booked       = serializers.SerializerMethodField()
    capacity_remaining    = serializers.SerializerMethodField()

    class Meta:
        model  = Doctor
        fields = (
            "id", "full_name", "department", "specialisation",
            "is_available", "max_patients_per_day",
            "todays_count", "is_fully_booked", "capacity_remaining",
        )

    def get_todays_count(self, obj):
        return obj.todays_appointment_count()

    def get_is_fully_booked(self, obj):
        return obj.is_fully_booked_today()

    def get_capacity_remaining(self, obj):
        return max(0, obj.max_patients_per_day - obj.todays_appointment_count())
