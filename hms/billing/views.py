"""
billing/views.py
================
InvoiceViewSet — full invoice lifecycle + payment recording.

RBAC per action
---------------
list, retrieve       → admin, receptionist (clinical staff can read their own patient invoices)
create               → admin, receptionist
update               → admin, receptionist (draft only)
destroy              → admin only
action               → admin, receptionist
payment              → admin, receptionist
items.*              → admin, receptionist
"""
import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsAdmin, IsAdminOrReceptionist, IsAnyStaff
from accounts.signals import write_audit, AuditAction
from .models import Invoice, InvoiceItem
from .serializers import (
    InvoiceListSerializer,
    InvoiceDetailSerializer,
    InvoiceCreateSerializer,
    InvoiceUpdateSerializer,
    InvoiceItemSerializer,
    InvoiceItemWriteSerializer,
    InvoiceActionSerializer,
    PaymentSerializer,
)

logger = logging.getLogger("hms.billing")


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    list            GET    /billing/invoices/
    create          POST   /billing/invoices/
    retrieve        GET    /billing/invoices/<id>/
    partial_update  PATCH  /billing/invoices/<id>/
    destroy         DELETE /billing/invoices/<id>/     → void if non-draft
    invoice_action  POST   /billing/invoices/<id>/action/
    payment         POST   /billing/invoices/<id>/payment/
    """
    queryset = (
        Invoice.objects
        .select_related("patient", "appointment", "created_by")
        .prefetch_related("items")
        .order_by("-created_at")
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "status":    ["exact", "in"],
        "currency":  ["exact"],
        "patient":   ["exact"],
        "issued_at": ["date", "gte", "lte"],
        "due_at":    ["date", "gte", "lte"],
    }
    search_fields   = [
        "invoice_number",
        "patient__first_name", "patient__last_name", "patient__mrn",
    ]
    ordering_fields = ["created_at", "due_at", "total_amount", "status"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAnyStaff()]
        if self.action == "destroy":
            return [IsAdmin()]
        return [IsAdminOrReceptionist()]

    def get_serializer_class(self):
        if self.action == "list":
            return InvoiceListSerializer
        if self.action == "create":
            return InvoiceCreateSerializer
        if self.action in ("partial_update", "update"):
            return InvoiceUpdateSerializer
        if self.action == "invoice_action":
            return InvoiceActionSerializer
        if self.action == "payment":
            return PaymentSerializer
        return InvoiceDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Clinical staff (doctor/nurse) can only see invoices for patients
        # they have records for — keeps billing isolated from clinical workflow.
        user = self.request.user
        if user.is_clinical_staff and not user.is_admin:
            if user.is_doctor and hasattr(user, "doctor_profile"):
                # Doctors see invoices for their own patients
                patient_ids = (
                    user.doctor_profile.appointments
                    .values_list("patient_id", flat=True)
                    .distinct()
                )
                qs = qs.filter(patient_id__in=patient_ids)
        return qs

    def perform_create(self, serializer):
        invoice = serializer.save(created_by=self.request.user)
        logger.info("Invoice %s created by %s", invoice.invoice_number, self.request.user.email)

    def perform_destroy(self, instance):
        """Void instead of delete for non-draft invoices."""
        if instance.status == "draft":
            instance.delete()
        else:
            try:
                instance.void()
            except Exception as exc:
                from rest_framework.exceptions import ValidationError
                raise ValidationError(str(exc))

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="action")
    def invoice_action(self, request, pk=None):
        """
        POST /billing/invoices/<id>/action/
        Body: { "action": "issue" | "mark_overdue" | "void" }
        """
        invoice    = self.get_object()
        serializer = InvoiceActionSerializer(
            data=request.data,
            context={"invoice": invoice, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        action_name = serializer.validated_data["action"]
        try:
            getattr(invoice, action_name)()
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        write_audit(
            action=AuditAction.UPDATE,
            table_name="billing_invoice",
            record_id=invoice.pk,
            user=request.user,
            new_value={"action": action_name, "new_status": invoice.status},
        )
        logger.info("Invoice %s action '%s' by %s", invoice.invoice_number, action_name, request.user.email)
        return Response(InvoiceDetailSerializer(invoice, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="payment")
    def payment(self, request, pk=None):
        """
        POST /billing/invoices/<id>/payment/
        Records a full or partial payment.
        """
        invoice    = self.get_object()
        serializer = PaymentSerializer(
            data=request.data,
            context={"invoice": invoice, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]
        try:
            invoice.record_payment(amount)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        write_audit(
            action=AuditAction.UPDATE,
            table_name="billing_invoice",
            record_id=invoice.pk,
            user=request.user,
            new_value={
                "payment": str(amount),
                "method":  serializer.validated_data.get("payment_method"),
                "balance": str(invoice.balance_due),
            },
        )
        return Response(InvoiceDetailSerializer(invoice, context={"request": request}).data)


class InvoiceItemViewSet(viewsets.ModelViewSet):
    """
    Nested under /billing/invoices/<invoice_pk>/items/

    list            GET    /billing/invoices/<invoice_pk>/items/
    create          POST   /billing/invoices/<invoice_pk>/items/
    retrieve        GET    /billing/invoices/<invoice_pk>/items/<id>/
    partial_update  PATCH  /billing/invoices/<invoice_pk>/items/<id>/
    destroy         DELETE /billing/invoices/<invoice_pk>/items/<id>/
    """
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAnyStaff()]
        return [IsAdminOrReceptionist()]

    def get_queryset(self):
        return InvoiceItem.objects.filter(invoice_id=self.kwargs["invoice_pk"])

    def get_serializer_class(self):
        if self.action == "list":
            return InvoiceItemSerializer
        return InvoiceItemWriteSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        try:
            ctx["invoice"] = Invoice.objects.get(pk=self.kwargs["invoice_pk"])
        except Invoice.DoesNotExist:
            pass
        return ctx

    def perform_create(self, serializer):
        invoice = Invoice.objects.get(pk=self.kwargs["invoice_pk"])
        if not invoice.is_editable:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot add items to a non-draft invoice.")
        serializer.save(invoice=invoice)
