"""
patients/views.py
=================
PatientViewSet — CRUD + search + soft-delete.

RBAC per action
---------------
list, retrieve          → any authenticated staff
create, update          → admin, receptionist
destroy                 → admin only (soft-delete)
export                  → admin only
medical_history         → clinical staff (doctor, nurse, admin)
"""

import csv
import io
import logging

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import (
    IsAdmin,
    IsAdminOrReceptionist,
    IsClinicalStaff,
    IsPatientDataOwner,
    IsAnyStaff,
)
from accounts.signals import write_audit, AuditAction
from .models import Patient
from .serializers import (
    PatientListSerializer,
    PatientDetailSerializer,
    PatientMinimalSerializer,
    PatientDeactivateSerializer,
)

logger = logging.getLogger("hms.patients")


class PatientViewSet(viewsets.ModelViewSet):
    """
    list            GET    /patients/
    create          POST   /patients/
    retrieve        GET    /patients/<id>/
    partial_update  PATCH  /patients/<id>/
    destroy         DELETE /patients/<id>/          → soft-deactivate
    medical_history GET    /patients/<id>/history/
    export          GET    /patients/export/         → CSV (admin only)
    search_quick    GET    /patients/search/         → minimal results for autocomplete
    """

    queryset = (
        Patient.objects
        .select_related("created_by")
        .order_by("last_name", "first_name")
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["gender", "blood_type", "is_active", "is_diabetic", "is_hypertensive"]
    search_fields    = [
        "first_name", "last_name", "mrn", "phone",
        "email", "national_id", "insurance_number",
    ]
    ordering_fields  = ["last_name", "first_name", "created_at", "date_of_birth"]
    ordering         = ["last_name", "first_name"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Default: active patients only (admins can pass ?is_active=false)
        if "is_active" not in self.request.query_params:
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.action in ("list", "search_quick"):
            return [IsAnyStaff()]
        if self.action == "retrieve":
            return [IsPatientDataOwner()]
        if self.action == "medical_history":
            return [IsClinicalStaff()]
        if self.action in ("create", "partial_update", "update"):
            return [IsAdminOrReceptionist()]
        if self.action in ("destroy", "export"):
            return [IsAdmin()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == "list":
            return PatientListSerializer
        if self.action == "search_quick":
            return PatientMinimalSerializer
        return PatientDetailSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    # ------------------------------------------------------------------
    # Standard actions
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        patient = serializer.save(created_by=self.request.user)
        logger.info("Patient %s registered by %s", patient.mrn, self.request.user.email)

    def perform_destroy(self, instance):
        """Soft-delete — patient records must be retained for medical-legal purposes."""
        serializer = PatientDeactivateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        instance.soft_delete()
        write_audit(
            action=AuditAction.DELETE,
            table_name="patients_patient",
            record_id=instance.pk,
            user=self.request.user,
            old_value={"mrn": instance.mrn, "is_active": True},
            new_value={"is_active": False},
        )
        logger.info("Patient %s soft-deleted by %s", instance.mrn, self.request.user.email)

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="history")
    def medical_history(self, request, pk=None):
        """GET /patients/<id>/history/ — full chronological EHR list."""
        patient = self.get_object()
        records = patient.medical_records.select_related("doctor", "appointment").order_by("-recorded_at")

        # Import here to avoid circular import at module level
        from records.serializers import MedicalRecordListSerializer
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = MedicalRecordListSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = MedicalRecordListSerializer(records, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="search")
    def search_quick(self, request):
        """
        GET /patients/search/?q=<term>
        Lightweight autocomplete — returns minimal fields only.
        Used by appointment booking and invoice creation forms.
        """
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            return Response([], status=status.HTTP_200_OK)

        patients = (
            Patient.objects.active()
            .filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(mrn__icontains=q)
                | Q(phone__icontains=q)
            )[:20]
        )
        serializer = PatientMinimalSerializer(patients, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        """
        GET /patients/export/?format=csv
        Admin-only CSV export. Audit-logged.
        """
        patients = self.filter_queryset(self.get_queryset())

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "MRN", "First Name", "Last Name", "Date of Birth", "Gender",
            "Blood Type", "Phone", "Email", "Insurance Provider", "Created At",
        ])
        for p in patients:
            writer.writerow([
                p.mrn, p.first_name, p.last_name, p.date_of_birth,
                p.gender, p.blood_type or "", p.phone, p.email or "",
                p.insurance_provider or "", p.created_at.date(),
            ])

        write_audit(
            action=AuditAction.EXPORT,
            table_name="patients_patient",
            record_id=None,
            user=request.user,
            new_value={"format": "csv", "count": patients.count()},
        )

        from django.http import HttpResponse
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="patients.csv"'
        return response
