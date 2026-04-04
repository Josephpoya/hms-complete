"""
doctors/views.py
================
DoctorViewSet + DoctorAvailabilityViewSet.

RBAC per action
---------------
list, retrieve       → any staff
create, update       → admin only
destroy              → admin only (soft via is_available=False)
availability.*       → admin only for write, any staff for read
workload             → any staff (dashboard widget)
"""
import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsAdmin, IsAnyStaff
from .models import Doctor, DoctorAvailability
from .serializers import (
    DoctorListSerializer,
    DoctorDetailSerializer,
    DoctorAvailabilitySerializer,
    DoctorWorkloadSerializer,
    DoctorMinimalSerializer,
)

logger = logging.getLogger("hms.doctors")


class DoctorViewSet(viewsets.ModelViewSet):
    """
    list            GET    /doctors/
    create          POST   /doctors/
    retrieve        GET    /doctors/<id>/
    partial_update  PATCH  /doctors/<id>/
    destroy         DELETE /doctors/<id>/
    workload        GET    /doctors/workload/
    available       GET    /doctors/available/
    """
    queryset = (
        Doctor.objects
        .select_related("user")
        .prefetch_related("availability")
        .order_by("last_name", "first_name")
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["department", "is_available", "accepts_walk_in"]
    search_fields    = ["first_name", "last_name", "specialisation", "licence_number"]
    ordering_fields  = ["last_name", "specialisation", "department", "consultation_fee"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "workload", "available"):
            return [IsAnyStaff()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == "list":
            return DoctorListSerializer
        if self.action in ("workload", "available"):
            return DoctorWorkloadSerializer
        return DoctorDetailSerializer

    def perform_destroy(self, instance):
        """Mark unavailable rather than deleting — appointments reference this record."""
        instance.is_available = False
        instance.save(update_fields=["is_available", "updated_at"])
        # Also deactivate the linked user account
        instance.user.deactivate()
        logger.info("Doctor %s deactivated by %s", instance.full_name, self.request.user.email)

    @action(detail=False, methods=["get"], url_path="workload")
    def workload(self, request):
        """GET /doctors/workload/ — all doctors with today's patient count."""
        doctors = self.filter_queryset(self.get_queryset().filter(is_available=True))
        serializer = DoctorWorkloadSerializer(doctors, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="available")
    def available(self, request):
        """GET /doctors/available/?department=surgery — available doctors for booking."""
        doctors = self.filter_queryset(
            self.get_queryset().filter(is_available=True)
        )
        serializer = DoctorWorkloadSerializer(doctors, many=True, context={"request": request})
        return Response(serializer.data)


class DoctorAvailabilityViewSet(viewsets.ModelViewSet):
    """
    Nested under /doctors/<doctor_pk>/availability/

    list            GET    /doctors/<doctor_pk>/availability/
    create          POST   /doctors/<doctor_pk>/availability/
    retrieve        GET    /doctors/<doctor_pk>/availability/<id>/
    partial_update  PATCH  /doctors/<doctor_pk>/availability/<id>/
    destroy         DELETE /doctors/<doctor_pk>/availability/<id>/
    """
    serializer_class  = DoctorAvailabilitySerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAnyStaff()]
        return [IsAdmin()]

    def get_queryset(self):
        return (
            DoctorAvailability.objects
            .filter(doctor_id=self.kwargs["doctor_pk"])
            .order_by("weekday", "start_time")
        )

    def perform_create(self, serializer):
        doctor = Doctor.objects.get(pk=self.kwargs["doctor_pk"])
        serializer.save(doctor=doctor)
