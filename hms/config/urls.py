"""
config/urls.py
==============
Root URL configuration for the HMS API.

All application routes are versioned under /api/v1/.
The router structure is:

  /api/v1/auth/           → accounts auth endpoints (login, logout, me, users)
  /api/v1/patients/       → PatientViewSet
  /api/v1/doctors/        → DoctorViewSet + nested DoctorAvailabilityViewSet
  /api/v1/appointments/   → AppointmentViewSet
  /api/v1/billing/        → InvoiceViewSet + nested InvoiceItemViewSet
  /api/v1/pharmacy/       → DrugViewSet + PrescriptionViewSet
  /api/v1/records/        → MedicalRecordViewSet + AuditLogViewSet (admin)

OpenAPI schema:
  /api/schema/            → raw OpenAPI JSON
  /api/schema/swagger/    → Swagger UI (disabled in production via setting)
  /api/schema/redoc/      → ReDoc (disabled in production)
"""

from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# ---------------------------------------------------------------------------
# API v1 URL patterns — imported from each app's urls.py
# ---------------------------------------------------------------------------

api_v1_patterns = [
    path("auth/",         include("accounts.urls")),
    path("patients/",     include("patients.urls")),
    path("doctors/",      include("doctors.urls")),
    path("appointments/", include("appointments.urls")),
    path("billing/",      include("billing.urls")),
    path("pharmacy/",     include("pharmacy.urls")),
    path("records/",      include("records.urls")),
]

# ---------------------------------------------------------------------------
# OpenAPI docs (only enabled in non-production environments)
# ---------------------------------------------------------------------------

schema_patterns = [
    path("schema/",          SpectacularAPIView.as_view(),                       name="schema"),
    path("schema/swagger/",  SpectacularSwaggerView.as_view(url_name="schema"),  name="swagger-ui"),
    path("schema/redoc/",    SpectacularRedocView.as_view(url_name="schema"),    name="redoc"),
]

# ---------------------------------------------------------------------------
# Root URL patterns
# ---------------------------------------------------------------------------

urlpatterns = [
    # Django admin (internal tooling — protected by VPN in production)
    path("admin/", admin.site.urls),

    # API v1
    path("api/v1/", include(api_v1_patterns)),
]

# Only expose API docs in non-production environments
if settings.DEBUG:
    urlpatterns += [path("api/", include(schema_patterns))]
