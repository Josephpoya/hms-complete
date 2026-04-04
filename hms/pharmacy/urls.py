from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"drugs",         views.DrugViewSet,         basename="drug")
router.register(r"prescriptions", views.PrescriptionViewSet, basename="prescription")

urlpatterns = [path("", include(router.urls))]
