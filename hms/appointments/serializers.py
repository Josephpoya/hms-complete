"""
appointments/serializers.py
===========================
Appointment serializers with full state-machine and conflict validation.

  AppointmentListSerializer    — lightweight list view.
  AppointmentDetailSerializer  — full create/retrieve with overlap validation.
  AppointmentStatusSerializer  — status-change only (enforces state machine).
  AppointmentCalendarSerializer — date-range calendar data for frontend widgets.

Conflict validation (applied in AppointmentDetailSerializer.validate)
----------------------------------------------------------------------
1. scheduled_at must be in the future.
2. The doctor must be available (is_available=True).
3. The doctor must not be fully booked today.
4. No existing active appointment for the same doctor overlaps in duration.
5. No existing active appointment for the same patient overlaps (double-visit guard).

These checks mirror the model's clean() method but produce DRF-friendly
error dicts rather than Django ValidationError.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from patients.serializers import PatientMinimalSerializer
from doctors.serializers import DoctorMinimalSerializer
from .models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    STATUS_TRANSITIONS,
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class AppointmentListSerializer(serializers.ModelSerializer):
    patient_name     = serializers.CharField(source="patient.full_name",  read_only=True)
    patient_mrn      = serializers.CharField(source="patient.mrn",        read_only=True)
    doctor_name      = serializers.CharField(source="doctor.full_name",   read_only=True)
    doctor_dept      = serializers.CharField(source="doctor.department",  read_only=True)
    end_time         = serializers.ReadOnlyField()
    duration_display = serializers.ReadOnlyField()
    status_display   = serializers.CharField(source="get_status_display", read_only=True)
    type_display     = serializers.CharField(source="get_appointment_type_display", read_only=True)

    class Meta:
        model  = Appointment
        fields = (
            "id",
            "patient_name",
            "patient_mrn",
            "doctor_name",
            "doctor_dept",
            "scheduled_at",
            "end_time",
            "duration_minutes",
            "duration_display",
            "status",
            "status_display",
            "appointment_type",
            "type_display",
            "priority",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

class AppointmentDetailSerializer(serializers.ModelSerializer):
    """
    Used for POST (create) and GET (retrieve).
    Status changes must go through AppointmentStatusSerializer.
    """
    # Read-only nested representations
    patient_detail       = PatientMinimalSerializer(source="patient",    read_only=True)
    doctor_detail        = DoctorMinimalSerializer(source="doctor",      read_only=True)
    end_time             = serializers.ReadOnlyField()
    duration_display     = serializers.ReadOnlyField()
    is_active            = serializers.ReadOnlyField()
    is_terminal          = serializers.ReadOnlyField()
    allowed_transitions  = serializers.ReadOnlyField()
    created_by_email     = serializers.CharField(source="created_by.email", read_only=True, default=None)

    # Write-only FK fields accepted at creation
    patient = serializers.PrimaryKeyRelatedField(
        queryset=__import__("patients.models", fromlist=["Patient"]).Patient.objects.filter(is_active=True)
    )
    doctor = serializers.PrimaryKeyRelatedField(
        queryset=__import__("doctors.models", fromlist=["Doctor"]).Doctor.objects.filter(is_available=True)
    )

    class Meta:
        model  = Appointment
        fields = (
            "id",
            # Write FKs
            "patient",
            "doctor",
            # Read nested
            "patient_detail",
            "doctor_detail",
            # Scheduling
            "scheduled_at",
            "end_time",
            "duration_minutes",
            "duration_display",
            "appointment_type",
            "priority",
            # State
            "status",
            "is_active",
            "is_terminal",
            "allowed_transitions",
            # Content
            "chief_complaint",
            "notes",
            "cancellation_reason",
            # Audit
            "created_by_email",
            "reminder_sent_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "patient_detail",
            "doctor_detail",
            "end_time",
            "duration_display",
            "is_active",
            "is_terminal",
            "allowed_transitions",
            "status",               # change via AppointmentStatusSerializer
            "cancellation_reason",  # set via status change
            "created_by_email",
            "reminder_sent_at",
            "created_at",
            "updated_at",
        )

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    def validate_scheduled_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError(
                "Appointment must be scheduled at a future date and time."
            )
        # No bookings more than 90 days out (configurable)
        max_advance = timezone.now() + timedelta(days=90)
        if value > max_advance:
            raise serializers.ValidationError(
                "Appointments cannot be booked more than 90 days in advance."
            )
        return value

    def validate_priority(self, value):
        if not (1 <= value <= 4):
            raise serializers.ValidationError("Priority must be 1 (emergency) to 4 (elective).")
        return value

    # ------------------------------------------------------------------
    # Object-level validation — conflict detection
    # ------------------------------------------------------------------

    def validate(self, attrs):
        doctor       = attrs.get("doctor") or (self.instance and self.instance.doctor)
        patient      = attrs.get("patient") or (self.instance and self.instance.patient)
        scheduled_at = attrs.get("scheduled_at") or (self.instance and self.instance.scheduled_at)
        duration     = attrs.get("duration_minutes") or (self.instance and self.instance.duration_minutes) or 30

        errors = {}

        if doctor and scheduled_at:
            end_time = scheduled_at + timedelta(minutes=duration)

            # 1. Doctor availability flag
            if not doctor.is_available:
                errors["doctor"] = f"Dr. {doctor.full_name} is currently marked as unavailable."

            # 2. Doctor fully booked today
            if doctor.is_fully_booked_today():
                errors["doctor"] = (
                    f"Dr. {doctor.full_name} has reached the maximum of "
                    f"{doctor.max_patients_per_day} patients for today."
                )

            # 3. Doctor slot overlap
            overlapping_doctor = (
                Appointment.objects
                .filter(
                    doctor=doctor,
                    status__in=ACTIVE_STATUSES,
                    scheduled_at__lt=end_time,
                )
                .exclude(pk=self.instance.pk if self.instance else None)
            )
            for other in overlapping_doctor:
                if other.end_time > scheduled_at:
                    errors["scheduled_at"] = (
                        f"Dr. {doctor.full_name} already has an appointment from "
                        f"{other.scheduled_at:%H:%M} to {other.end_time:%H:%M}. "
                        f"Choose a different time slot."
                    )
                    break

        if patient and scheduled_at:
            end_time = scheduled_at + timedelta(minutes=duration)

            # 4. Patient double-visit guard (same patient, overlapping time)
            overlapping_patient = (
                Appointment.objects
                .filter(
                    patient=patient,
                    status__in=ACTIVE_STATUSES,
                    scheduled_at__lt=end_time,
                )
                .exclude(pk=self.instance.pk if self.instance else None)
            )
            for other in overlapping_patient:
                if other.end_time > scheduled_at:
                    errors["patient"] = (
                        f"This patient already has an appointment at "
                        f"{other.scheduled_at:%H:%M} with {other.doctor.full_name}."
                    )
                    break

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    # ------------------------------------------------------------------
    # Create / update
    # ------------------------------------------------------------------

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        instance = Appointment(**validated_data)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        # Prevent rescheduling a terminal appointment
        if instance.is_terminal:
            raise serializers.ValidationError(
                f"Cannot modify a {instance.status} appointment."
            )
        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Status change
# ---------------------------------------------------------------------------

class AppointmentStatusSerializer(serializers.Serializer):
    """
    Used exclusively by PATCH /appointments/<id>/status/.
    Enforces the state machine and collects cancellation reason when needed.
    """
    status              = serializers.ChoiceField(choices=AppointmentStatus.choices)
    cancellation_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        help_text="Required when transitioning to 'cancelled'.",
    )

    def validate(self, attrs):
        appointment = self.context["appointment"]
        new_status  = attrs["status"]

        # 1. State machine check
        if not appointment.can_transition_to(new_status):
            allowed = sorted(appointment.allowed_transitions)
            raise serializers.ValidationError(
                {
                    "status": (
                        f"Cannot move from '{appointment.get_status_display()}' "
                        f"to '{new_status}'. "
                        f"Allowed transitions: {allowed or ['none — terminal state']}."
                    )
                }
            )

        # 2. Cancellation reason required
        if new_status == AppointmentStatus.CANCELLED:
            if not attrs.get("cancellation_reason", "").strip():
                raise serializers.ValidationError(
                    {"cancellation_reason": "A reason is required when cancelling an appointment."}
                )

        return attrs


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

class AppointmentCalendarSerializer(serializers.ModelSerializer):
    """
    Compact serializer for calendar/schedule views.
    Returns only fields needed to render a calendar tile.
    """
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    doctor_name  = serializers.CharField(source="doctor.full_name",  read_only=True)
    end_time     = serializers.ReadOnlyField()
    color_code   = serializers.SerializerMethodField()

    class Meta:
        model  = Appointment
        fields = (
            "id",
            "patient_name",
            "doctor_name",
            "scheduled_at",
            "end_time",
            "duration_minutes",
            "appointment_type",
            "status",
            "priority",
            "color_code",
        )

    def get_color_code(self, obj):
        """Semantic colour hints for the calendar frontend."""
        COLOR_MAP = {
            AppointmentStatus.BOOKED:      "#378ADD",
            AppointmentStatus.CHECKED_IN:  "#1D9E75",
            AppointmentStatus.IN_PROGRESS: "#EF9F27",
            AppointmentStatus.COMPLETED:   "#888780",
            AppointmentStatus.CANCELLED:   "#E24B4A",
            AppointmentStatus.NO_SHOW:     "#D85A30",
        }
        return COLOR_MAP.get(obj.status, "#888780")


# ---------------------------------------------------------------------------
# Reminder update
# ---------------------------------------------------------------------------

class AppointmentReminderSerializer(serializers.ModelSerializer):
    """Internal: updated by Celery task after sending a reminder."""
    class Meta:
        model  = Appointment
        fields = ("reminder_sent_at",)
