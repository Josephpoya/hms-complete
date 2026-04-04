from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers
from . import views

router = DefaultRouter()
router.register(r"invoices", views.InvoiceViewSet, basename="invoice")

items_router = nested_routers.NestedDefaultRouter(router, r"invoices", lookup="invoice")
items_router.register(r"items", views.InvoiceItemViewSet, basename="invoice-item")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(items_router.urls)),
]
