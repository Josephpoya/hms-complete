"""
records/views.py
================
MedicalRecordViewSet + AuditLogViewSet.

RBAC per action
---------------
MedicalRecord:
  list, retrieve      → clinical staff (doctor, nurse, admin)
  create              → doctor only
  partial_update      → doctor only (own records, within 24h)
  destroy             → blocked (records are permanent)
  add_attachment      → clinical staff
  remove_attachment   → authoring doctor or admin
  lock                → admin only (or Celery task)
  patient_records     → clinical staff

AuditLog:
  list, retrieve      → admin only
"""
import logging
import uuid

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from accounts.permissions import IsAdmin, IsDoctor, IsClinicalStaff
from accounts.signals import write_audit, AuditAction
from .models import MedicalRecord
from .serializers import (
    MedicalRecordListSerializer,
    MedicalRecordDetailSerializer,
    MedicalRecordCreateSerializer,
    MedicalRecordUpdateSerializer,
    AttachmentUploadSerializer,
    AuditLogSerializer,
)

logger = logging.getLogger("hms.records")


class MedicalRecordViewSet(viewsets.ModelViewSet):
    """
    list                GET    /records/
    create              POST   /records/
    retrieve            GET    /records/<id>/
    partial_update      PATCH  /records/<id>/
    add_attachment      POST   /records/<id>/attachments/
    remove_attachment   DELETE /records/<id>/attachments/<key>/
    lock                POST   /records/<id>/lock/
    patient_records     GET    /records/patient/<patient_id>/
    """
    queryset = (
        MedicalRecord.objects
        .select_related("patient", "doctor", "doctor__user", "appointment")
        .prefetch_related("prescriptions")
        .order_by("-recorded_at")
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "is_locked":   ["exact"],
        "icd10_code":  ["exact", "icontains"],
        "doctor":      ["exact"],
        "patient":     ["exact"],
        "recorded_at": ["date", "gte", "lte"],
    }
    search_fields   = [
        "patient__first_name", "patient__last_name", "patient__mrn",
        "icd10_code", "icd10_description",
    ]
    ordering_fields = ["recorded_at", "is_locked"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [IsDoctor()]
        if self.action in ("partial_update", "update", "lock"):
            return [IsDoctor()]
        if self.action == "remove_attachment":
            return [IsClinicalStaff()]
        return [IsClinicalStaff()]

    def get_serializer_class(self):
        if self.action == "list":
            return MedicalRecordListSerializer
        if self.action == "create":
            return MedicalRecordCreateSerializer
        if self.action in ("partial_update", "update"):
            return MedicalRecordUpdateSerializer
        return MedicalRecordDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Doctors can only UPDATE their own records; they can READ all
        if self.action in ("partial_update", "update") and user.is_doctor:
            if hasattr(user, "doctor_profile"):
                qs = qs.filter(doctor=user.doctor_profile)
        return qs

    def perform_create(self, serializer):
        record = serializer.save()
        logger.info(
            "Medical record created for patient %s by %s",
            record.patient.mrn, self.request.user.email,
        )

    def destroy(self, request, *args, **kwargs):
        """Medical records are permanent — hard delete is never permitted."""
        return Response(
            {"error": "Medical records cannot be deleted. They are permanent legal documents."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # ------------------------------------------------------------------
    # Attachment actions
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="attachments",
        parser_classes=[MultiPartParser, FormParser],
    )
    def add_attachment(self, request, pk=None):
        """POST /records/<id>/attachments/ — upload file to S3, register reference."""
        record     = self.get_object()
        serializer = AttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        s3_key = f"records/{record.patient_id}/{record.pk}/{uuid.uuid4()}_{uploaded_file.name}"

        try:
            import boto3
            from django.conf import settings
            s3 = boto3.client("s3", region_name=settings.AWS_S3_REGION_NAME)
            s3.upload_fileobj(
                uploaded_file,
                settings.AWS_STORAGE_BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": uploaded_file.content_type},
            )
        except Exception as exc:
            logger.error("S3 upload failed: %s", exc)
            return Response(
                {"error": f"File upload failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        record.add_attachment(
            key=s3_key,
            filename=uploaded_file.name,
            content_type=uploaded_file.content_type,
            size_bytes=uploaded_file.size,
        )
        logger.info("Attachment %s added to record %s", uploaded_file.name, record.pk)
        return Response(
            {"detail": "File uploaded successfully.", "key": s3_key},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path=r"attachments/(?P<key>[^/.]+)")
    def remove_attachment(self, request, pk=None, key=None):
        """DELETE /records/<id>/attachments/<key>/"""
        record = self.get_object()
        try:
            record.remove_attachment(key)
        except (ValueError, Exception) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Attachment removed."}, status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # Admin lock action
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="lock", permission_classes=[IsAdmin])
    def lock(self, request, pk=None):
        """POST /records/<id>/lock/ — manually lock a record ahead of the 24h window."""
        record = self.get_object()
        if record.is_locked:
            return Response(
                {"detail": "Record is already locked."},
                status=status.HTTP_200_OK,
            )
        record.lock()
        write_audit(
            action=AuditAction.UPDATE,
            table_name="records_medicalrecord",
            record_id=record.pk,
            user=request.user,
            new_value={"is_locked": True, "action": "manual_lock"},
        )
        return Response({"detail": "Record locked successfully."})

    # ------------------------------------------------------------------
    # Patient-scoped list
    # ------------------------------------------------------------------

    @action(detail=False, methods=["get"], url_path=r"patient/(?P<patient_id>[0-9a-f-]+)")
    def patient_records(self, request, patient_id=None):
        """GET /records/patient/<patient_id>/ — all records for one patient."""
        records = (
            self.get_queryset()
            .filter(patient_id=patient_id)
            .order_by("-recorded_at")
        )
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = MedicalRecordListSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = MedicalRecordListSerializer(records, many=True, context={"request": request})
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Audit log (admin-only)
# ---------------------------------------------------------------------------

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /records/audit/          — list audit events
    GET /records/audit/<id>/     — retrieve one event
    """
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["action", "table_name", "user"]
    search_fields    = ["user_email_snapshot", "table_name", "action"]
    ordering_fields  = ["created_at", "action", "table_name"]
    ordering         = ["-created_at"]

    def get_queryset(self):
        from accounts.signals import AuditLog
        return AuditLog.objects.select_related("user").all()
