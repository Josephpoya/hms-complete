from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers
from . import views

router = DefaultRouter()
router.register(r"", views.DoctorViewSet, basename="doctor")

# Nested: /doctors/<doctor_pk>/availability/
availability_router = nested_routers.NestedDefaultRouter(router, r"", lookup="doctor")
availability_router.register(r"availability", views.DoctorAvailabilityViewSet, basename="doctor-availability")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(availability_router.urls)),
]
