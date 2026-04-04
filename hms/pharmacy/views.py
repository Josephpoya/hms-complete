"""
pharmacy/views.py
=================
DrugViewSet + PrescriptionViewSet.

RBAC per action
---------------
Drug:
  list, retrieve    → any staff
  create, update    → admin only
  destroy           → admin only (soft via is_active=False)
  restock           → admin only

Prescription:
  list              → clinical staff
  create            → doctor only
  retrieve          → clinical staff
  change_status     → nurse or admin (dispense/cancel)
  dispense          → nurse or admin
  cancel            → doctor, admin
"""
import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import (
    IsAdmin,
    IsAdminOrNurse,
    IsDoctor,
    IsClinicalStaff,
    IsAnyStaff,
)
from accounts.signals import write_audit, AuditAction
from .models import Drug, Prescription, PrescriptionStatus
from .serializers import (
    DrugListSerializer,
    DrugDetailSerializer,
    DrugStockUpdateSerializer,
    PrescriptionListSerializer,
    PrescriptionDetailSerializer,
    PrescriptionCreateSerializer,
    DispenseSerializer,
    PrescriptionCancelSerializer,
)

logger = logging.getLogger("hms.pharmacy")


class DrugViewSet(viewsets.ModelViewSet):
    """
    list            GET    /pharmacy/drugs/
    create          POST   /pharmacy/drugs/
    retrieve        GET    /pharmacy/drugs/<id>/
    partial_update  PATCH  /pharmacy/drugs/<id>/
    destroy         DELETE /pharmacy/drugs/<id>/     → deactivate
    restock         POST   /pharmacy/drugs/<id>/restock/
    low_stock       GET    /pharmacy/drugs/low-stock/
    expiring        GET    /pharmacy/drugs/expiring/
    """
    queryset = Drug.objects.order_by("generic_name", "name")
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "category":             ["exact"],
        "is_active":            ["exact"],
        "requires_prescription": ["exact"],
        "controlled_drug":      ["exact"],
        "expiry_date":          ["lte", "gte"],
    }
    search_fields   = ["name", "generic_name", "barcode", "strength"]
    ordering_fields = ["name", "generic_name", "stock_quantity", "expiry_date", "category"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "low_stock", "expiring"):
            return [IsAnyStaff()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == "list":
            return DrugListSerializer
        if self.action == "restock":
            return DrugStockUpdateSerializer
        return DrugDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Default: active drugs only
        if "is_active" not in self.request.query_params:
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        logger.info("Drug %s deactivated by %s", instance.name, self.request.user.email)

    @action(detail=True, methods=["post"], url_path="restock")
    def restock(self, request, pk=None):
        """POST /pharmacy/drugs/<id>/restock/"""
        drug       = self.get_object()
        serializer = DrugStockUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        qty          = serializer.validated_data["quantity"]
        batch        = serializer.validated_data.get("batch_number")
        expiry       = serializer.validated_data.get("expiry_date")
        old_stock    = drug.stock_quantity

        drug.restock(qty, batch_number=batch, expiry_date=expiry)

        write_audit(
            action=AuditAction.UPDATE,
            table_name="pharmacy_drug",
            record_id=drug.pk,
            user=request.user,
            old_value={"stock_quantity": old_stock},
            new_value={"stock_quantity": drug.stock_quantity, "restocked": qty},
        )
        return Response(DrugDetailSerializer(drug, context={"request": request}).data)

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        """GET /pharmacy/drugs/low-stock/ — drugs at or below reorder level."""
        from django.db.models import F
        drugs = Drug.objects.active().filter(stock_quantity__lte=F("reorder_level")).order_by("stock_quantity")
        page  = self.paginate_queryset(drugs)
        if page is not None:
            return self.get_paginated_response(
                DrugListSerializer(page, many=True, context={"request": request}).data
            )
        return Response(DrugListSerializer(drugs, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], url_path="expiring")
    def expiring(self, request):
        """GET /pharmacy/drugs/expiring/?days=30 — drugs expiring within N days."""
        days = int(request.query_params.get("days", 30))
        drugs = Drug.objects.active().expiring_soon(days=days).order_by("expiry_date")
        page  = self.paginate_queryset(drugs)
        if page is not None:
            return self.get_paginated_response(
                DrugListSerializer(page, many=True, context={"request": request}).data
            )
        return Response(DrugListSerializer(drugs, many=True, context={"request": request}).data)


class PrescriptionViewSet(viewsets.ModelViewSet):
    """
    list            GET    /pharmacy/prescriptions/
    create          POST   /pharmacy/prescriptions/
    retrieve        GET    /pharmacy/prescriptions/<id>/
    dispense        POST   /pharmacy/prescriptions/<id>/dispense/
    cancel          POST   /pharmacy/prescriptions/<id>/cancel/
    """
    queryset = (
        Prescription.objects
        .select_related("patient", "doctor", "drug", "medical_record", "dispensed_by")
        .order_by("-prescribed_at")
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "status":  ["exact", "in"],
        "doctor":  ["exact"],
        "patient": ["exact"],
        "drug":    ["exact"],
    }
    search_fields   = [
        "patient__first_name", "patient__last_name", "patient__mrn",
        "drug__name", "drug__generic_name",
    ]
    ordering_fields = ["prescribed_at", "status"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [IsDoctor()]
        if self.action == "dispense":
            return [IsAdminOrNurse()]
        if self.action == "cancel":
            return [IsClinicalStaff()]
        return [IsClinicalStaff()]

    def get_serializer_class(self):
        if self.action == "list":
            return PrescriptionListSerializer
        if self.action == "create":
            return PrescriptionCreateSerializer
        if self.action == "dispense":
            return DispenseSerializer
        if self.action == "cancel":
            return PrescriptionCancelSerializer
        return PrescriptionDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Doctors see only their own prescriptions by default
        if user.is_doctor and hasattr(user, "doctor_profile"):
            qs = qs.filter(doctor=user.doctor_profile)
        return qs

    # Prevent PUT/PATCH on prescriptions — they are clinical records
    def update(self, request, *args, **kwargs):
        return Response(
            {"error": "Prescriptions cannot be edited. Cancel and reissue if needed."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"error": "Prescriptions cannot be deleted. Cancel via the /cancel/ endpoint."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["post"], url_path="dispense")
    def dispense(self, request, pk=None):
        """POST /pharmacy/prescriptions/<id>/dispense/"""
        prescription = self.get_object()
        serializer   = DispenseSerializer(
            data=request.data,
            context={"prescription": prescription, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            prescription.dispense(dispensed_by_user=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            "Prescription %s dispensed by %s",
            prescription.pk, request.user.email,
        )
        return Response(PrescriptionDetailSerializer(prescription, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """POST /pharmacy/prescriptions/<id>/cancel/"""
        prescription = self.get_object()
        serializer   = PrescriptionCancelSerializer(
            data=request.data,
            context={"prescription": prescription},
        )
        serializer.is_valid(raise_exception=True)

        try:
            prescription.cancel(reason=serializer.validated_data["reason"])
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PrescriptionDetailSerializer(prescription, context={"request": request}).data)
