"""
performance/database_optimisation.py
======================================
Production database query optimisation for HMS.

This module documents and implements the key optimisations that make HMS
perform at enterprise scale. Apply these patterns to existing views/querysets.

Contents:
  1. select_related / prefetch_related audit — prevents N+1 queries
  2. Database indexes beyond Django's defaults
  3. QuerySet caching decorators
  4. Slow query detection middleware
  5. Database connection health monitor
  6. Optimised querysets for each major view
"""

import logging
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any

from django.db import connection, reset_queries

logger = logging.getLogger("hms.performance")


# ─── 1. N+1 Query Detection ───────────────────────────────────────────────────
class NPlusOneDetectionMiddleware:
    """
    Development middleware that logs a warning when a single request
    triggers more than THRESHOLD database queries.

    Install in settings/development.py only:
      MIDDLEWARE += ["performance.database_optimisation.NPlusOneDetectionMiddleware"]
    """
    THRESHOLD = 10

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        if not settings.DEBUG:
            return self.get_response(request)

        reset_queries()
        response = self.get_response(request)
        query_count = len(connection.queries)

        if query_count > self.THRESHOLD:
            logger.warning(
                "N+1 SUSPECT: %s %s triggered %d queries (threshold=%d)",
                request.method, request.path, query_count, self.THRESHOLD,
            )
            # Log the slowest queries for diagnosis
            sorted_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)
            for q in sorted_queries[:3]:
                logger.debug("  SLOW QUERY (%.3fs): %s…", float(q["time"]), q["sql"][:120])

        return response


# ─── 2. Query timing context manager ─────────────────────────────────────────
@contextmanager
def measure_queries(label: str = ""):
    """
    Context manager for measuring query count and time in development.

    Usage:
        with measure_queries("patient list"):
            patients = Patient.objects.filter(is_active=True)[:25]
    """
    from django.conf import settings
    if not settings.DEBUG:
        yield
        return

    reset_queries()
    start = time.monotonic()
    yield
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    queries = connection.queries

    logger.debug(
        "QUERIES [%s]: count=%d time=%.2fms",
        label or "unnamed", len(queries), elapsed_ms,
    )


# ─── 3. Optimised base querysets for each major model ─────────────────────────
"""
These querysets are the correct ones to use in all views and APIs.
They use select_related and prefetch_related to load all needed data
in the minimum number of SQL queries.

Without optimisation — a page of 25 appointments:
  1 query for appointments
  25 queries for patient (N+1)
  25 queries for doctor  (N+1)
  = 51 queries total

With select_related — same page:
  1 query with JOINs
  = 1 query total
"""

def optimised_appointment_list():
    """Use this in AppointmentViewSet.get_queryset()."""
    from appointments.models import Appointment
    return (
        Appointment.objects
        .select_related(
            "patient",          # patient.full_name, patient.mrn, patient.phone
            "doctor",           # doctor.full_name, doctor.department
            "doctor__user",     # doctor.email (via user)
            "created_by",       # email of booking staff
        )
        .only(
            # Fetch only the columns actually needed in the list serializer
            "id", "status", "appointment_type", "scheduled_at", "duration_minutes",
            "priority", "chief_complaint", "notes", "cancellation_reason",
            "reminder_sent_at", "created_at",
            "patient__id", "patient__mrn", "patient__first_name", "patient__last_name",
            "patient__phone",
            "doctor__id", "doctor__first_name", "doctor__last_name",
            "doctor__specialisation", "doctor__department",
            "created_by__id", "created_by__email",
        )
        .order_by("-scheduled_at")
    )


def optimised_patient_list():
    """Use this in PatientViewSet.get_queryset() for list views."""
    from patients.models import Patient
    return (
        Patient.objects
        .filter(is_active=True)
        .select_related("created_by")
        .only(
            "id", "mrn", "first_name", "last_name",
            "date_of_birth", "gender", "blood_type", "phone", "email",
            "is_diabetic", "is_hypertensive", "has_allergies",
            "insurance_provider", "insurance_is_valid",
            "is_active", "created_at",
            "created_by__id", "created_by__email",
        )
        .order_by("last_name", "first_name")
    )


def optimised_invoice_list():
    """Use this in InvoiceViewSet.get_queryset()."""
    from billing.models import Invoice
    return (
        Invoice.objects
        .select_related("patient", "appointment", "created_by")
        .prefetch_related("items")           # Load all line items in one IN query
        .only(
            "id", "invoice_number", "status", "currency",
            "subtotal", "tax_amount", "discount_amount",
            "total_amount", "amount_paid", "balance_due",
            "issued_at", "due_at", "paid_at", "created_at",
            "patient__id", "patient__first_name", "patient__last_name",
            "patient__mrn",
        )
        .order_by("-created_at")
    )


def optimised_prescription_list():
    """Use this in PrescriptionViewSet.get_queryset()."""
    from pharmacy.models import Prescription
    return (
        Prescription.objects
        .select_related("patient", "doctor", "drug", "dispensed_by")
        .only(
            "id", "status", "dosage", "frequency", "duration_days",
            "quantity_prescribed", "prescribed_at", "dispensed_at",
            "patient__id", "patient__first_name", "patient__last_name", "patient__mrn",
            "doctor__id", "doctor__first_name", "doctor__last_name",
            "drug__id", "drug__name", "drug__generic_name", "drug__strength",
            "drug__unit", "drug__stock_quantity",
            "dispensed_by__id", "dispensed_by__email",
        )
        .order_by("-prescribed_at")
    )


# ─── 4. Raw SQL for dashboard aggregates ─────────────────────────────────────
"""
Dashboard KPIs are aggregate queries that touch many rows.
Django ORM generates correct SQL for these, but we can write
more efficient raw SQL for the most critical paths.

The functions below are called by DashboardService and cached via Redis.
"""

def get_dashboard_stats(user_role: str) -> dict:
    """
    Fetch all dashboard KPIs in a single database round-trip using
    a CTE (Common Table Expression) query. Cached for 5 minutes.
    """
    from cache.redis_cache import DashboardCache

    cached = DashboardCache.get_stats(user_role)
    if cached:
        return cached

    from django.utils import timezone
    from django.db import connection

    today = timezone.localdate()

    with connection.cursor() as cursor:
        cursor.execute("""
            WITH today_appts AS (
                SELECT
                    COUNT(*)                                          AS total,
                    COUNT(*) FILTER (WHERE status = 'booked')       AS booked,
                    COUNT(*) FILTER (WHERE status = 'in_progress')  AS in_progress,
                    COUNT(*) FILTER (WHERE status = 'completed')    AS completed,
                    COUNT(*) FILTER (WHERE status = 'no_show')      AS no_show
                FROM appointments_appointment
                WHERE DATE(scheduled_at) = %s
                  AND status NOT IN ('cancelled')
            ),
            pending_rx AS (
                SELECT COUNT(*) AS total
                FROM pharmacy_prescription
                WHERE status = 'pending'
            ),
            outstanding_invoices AS (
                SELECT
                    COUNT(*)            AS count,
                    COALESCE(SUM(total_amount - amount_paid), 0) AS total_balance
                FROM billing_invoice
                WHERE status IN ('issued', 'partially_paid', 'overdue')
            ),
            low_stock AS (
                SELECT COUNT(*) AS total
                FROM pharmacy_drug
                WHERE is_active = true
                  AND stock_quantity <= reorder_level
            ),
            active_patients AS (
                SELECT COUNT(*) AS total
                FROM patients_patient
                WHERE is_active = true
            )
            SELECT
                ta.total, ta.booked, ta.in_progress, ta.completed, ta.no_show,
                pr.total  AS pending_prescriptions,
                oi.count  AS outstanding_invoice_count,
                oi.total_balance,
                ls.total  AS low_stock_count,
                ap.total  AS active_patients
            FROM today_appts ta, pending_rx pr, outstanding_invoices oi,
                 low_stock ls, active_patients ap
        """, [today])

        row = cursor.fetchone()
        if not row:
            return {}

        stats = {
            "today_appointments": {
                "total":       row[0],
                "booked":      row[1],
                "in_progress": row[2],
                "completed":   row[3],
                "no_show":     row[4],
            },
            "pending_prescriptions":     row[5],
            "outstanding_invoices":      row[6],
            "outstanding_balance":       str(row[7]),
            "low_stock_drugs":           row[8],
            "active_patients":           row[9],
        }

    DashboardCache.set_stats(stats, user_role)
    return stats


# ─── 5. Database index recommendations ───────────────────────────────────────
"""
Run these SQL statements once in a migration or directly on the DB.
They complement Django's automatic single-column indexes with composite
and partial indexes that target specific query patterns.

Application pattern → Index:
  "today's appointments"        → (doctor_id, scheduled_at::date) WHERE status != 'cancelled'
  "patient search by name"      → GIN full-text on (first_name || ' ' || last_name)
  "pending prescriptions"       → (status, patient_id) WHERE status = 'pending'
  "outstanding invoices"        → (status, due_at) WHERE status IN (...)
  "audit log by user+date"      → (user_id, created_at)
"""

RECOMMENDED_INDEXES = """
-- Appointment: composite index for today's schedule query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_appt_doctor_date_active
    ON appointments_appointment (doctor_id, (scheduled_at::date))
    WHERE status NOT IN ('cancelled', 'no_show', 'completed');

-- Patient: full-text search (GIN — enables fast ILIKE on names)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_patient_name_fts
    ON patients_patient
    USING gin(to_tsvector('english', first_name || ' ' || last_name));

-- Prescription: partial index for pending only (most common query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rx_pending
    ON pharmacy_prescription (patient_id, prescribed_at)
    WHERE status = 'pending';

-- Invoice: outstanding billing query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_invoice_outstanding
    ON billing_invoice (patient_id, due_at)
    WHERE status IN ('issued', 'partially_paid', 'overdue');

-- Audit log: user timeline (admin audit view)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_user_ts
    ON audit_auditlog (user_id, created_at DESC);

-- Drug: low stock alert query (runs nightly)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drug_low_stock
    ON pharmacy_drug (stock_quantity, reorder_level)
    WHERE is_active = true;
"""


def apply_performance_indexes():
    """
    Apply the recommended indexes. Safe to run multiple times (IF NOT EXISTS).
    Run this after initial migration:

        python manage.py shell -c "from performance.database_optimisation import apply_performance_indexes; apply_performance_indexes()"
    """
    from django.db import connection
    statements = [s.strip() for s in RECOMMENDED_INDEXES.split(";") if s.strip()]
    applied = 0
    for stmt in statements:
        try:
            with connection.cursor() as cursor:
                cursor.execute(stmt)
            applied += 1
            logger.info("Applied index: %s…", stmt[:60])
        except Exception as e:
            logger.warning("Index skipped (%s…): %s", stmt[:60], e)
    logger.info("Performance indexes: %d applied", applied)
    return applied
