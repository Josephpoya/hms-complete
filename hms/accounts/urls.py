"""accounts/urls.py — auth + user management routes."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")

urlpatterns = [
    # Auth
    path("login/",          views.LoginView.as_view(),          name="auth-login"),
    path("logout/",         views.LogoutView.as_view(),         name="auth-logout"),
    path("refresh/",        TokenRefreshView.as_view(),         name="auth-refresh"),
    path("me/",             views.MeView.as_view(),             name="auth-me"),
    path("me/password/",    views.ChangePasswordView.as_view(), name="auth-change-password"),
    # User management (admin)
    path("", include(router.urls)),
]
