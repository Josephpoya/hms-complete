"""
appointments/views.py
=====================
AppointmentViewSet — full scheduling CRUD with state-machine actions.

RBAC per action
---------------
list, retrieve          → any staff
create                  → admin, receptionist
partial_update          → admin, receptionist (reschedule only)
destroy                 → admin, receptionist (triggers cancel)
change_status           → clinical staff (state-machine transition)
calendar                → any staff
today                   → any staff
send_reminder           → admin only (or Celery task)
"""
import logging

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import (
    IsAdmin,
    IsAdminOrReceptionist,
    IsClinicalStaff,
    IsAnyStaff,
)
from .models import Appointment, AppointmentStatus
from .serializers import (
    AppointmentListSerializer,
    AppointmentDetailSerializer,
    AppointmentStatusSerializer,
    AppointmentCalendarSerializer,
    AppointmentReminderSerializer,
)

logger = logging.getLogger("hms.appointments")


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    list            GET    /appointments/
    create          POST   /appointments/
    retrieve        GET    /appointments/<id>/
    partial_update  PATCH  /appointments/<id>/
    destroy         DELETE /appointments/<id>/     → triggers cancellation
    change_status   PATCH  /appointments/<id>/status/
    calendar        GET    /appointments/calendar/
    today           GET    /appointments/today/
    """
    queryset = (
        Appointment.objects
        .select_related("patient", "doctor", "doctor__user", "created_by")
        .order_by("-scheduled_at")
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "status":           ["exact", "in"],
        "appointment_type": ["exact"],
        "doctor":           ["exact"],
        "patient":          ["exact"],
        "priority":         ["exact", "lte", "gte"],
        "scheduled_at":     ["date", "gte", "lte"],
    }
    search_fields   = [
        "patient__first_name", "patient__last_name",
        "patient__mrn", "doctor__last_name",
    ]
    ordering_fields = ["scheduled_at", "status", "priority", "created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "calendar", "today"):
            return [IsAnyStaff()]
        if self.action == "change_status":
            return [IsClinicalStaff()]
        if self.action in ("create", "partial_update", "update", "destroy"):
            return [IsAdminOrReceptionist()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == "list":
            return AppointmentListSerializer
        if self.action == "change_status":
            return AppointmentStatusSerializer
        if self.action in ("calendar", "today"):
            return AppointmentCalendarSerializer
        return AppointmentDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Doctors see only their own appointments by default
        user = self.request.user
        if user.is_doctor and self.action in ("list", "calendar", "today"):
            if hasattr(user, "doctor_profile"):
                qs = qs.filter(doctor=user.doctor_profile)
        return qs

    def perform_create(self, serializer):
        appt = serializer.save(created_by=self.request.user)
        logger.info(
            "Appointment %s created for patient %s with Dr %s by %s",
            appt.id, appt.patient.mrn, appt.doctor.full_name, self.request.user.email,
        )

    def perform_destroy(self, instance):
        """DELETE triggers a cancellation rather than hard delete."""
        if instance.is_terminal:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                f"Cannot delete a {instance.get_status_display()} appointment."
            )
        instance.transition_to(AppointmentStatus.CANCELLED)
        logger.info("Appointment %s cancelled via DELETE by %s", instance.id, self.request.user.email)

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["patch"], url_path="status")
    def change_status(self, request, pk=None):
        """
        PATCH /appointments/<id>/status/
        The only correct way to transition appointment status.
        Enforces the state machine defined in STATUS_TRANSITIONS.
        """
        appointment = self.get_object()
        serializer  = AppointmentStatusSerializer(
            data=request.data,
            context={"appointment": appointment, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        if new_status == AppointmentStatus.CANCELLED:
            appointment.cancellation_reason = serializer.validated_data.get("cancellation_reason", "")
            appointment.save(update_fields=["cancellation_reason", "updated_at"])

        appointment.transition_to(new_status, actor=request.user)
        logger.info(
            "Appointment %s transitioned to %s by %s",
            appointment.id, new_status, request.user.email,
        )

        return Response(
            AppointmentDetailSerializer(appointment, context={"request": request}).data
        )

    @action(detail=False, methods=["get"], url_path="calendar")
    def calendar(self, request):
        """
        GET /appointments/calendar/?scheduled_at__gte=2024-01-01&scheduled_at__lte=2024-01-31
        Returns compact appointment data for calendar rendering.
        """
        qs = self.filter_queryset(self.get_queryset())
        serializer = AppointmentCalendarSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="today")
    def today(self, request):
        """GET /appointments/today/ — all appointments for the current day."""
        today = timezone.localdate()
        qs = self.filter_queryset(
            self.get_queryset().filter(scheduled_at__date=today).order_by("scheduled_at")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = AppointmentCalendarSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = AppointmentCalendarSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)
