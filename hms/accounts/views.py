"""
accounts/views.py
=================
Auth and user management viewsets.

Endpoints
---------
POST   /api/v1/auth/login/             CustomTokenObtainPairView
POST   /api/v1/auth/refresh/           TokenRefreshView (SimpleJWT)
POST   /api/v1/auth/logout/            LogoutView
GET    /api/v1/auth/me/                MeView
PATCH  /api/v1/auth/me/                MeView
POST   /api/v1/auth/me/password/       ChangePasswordView

GET    /api/v1/users/                  UserViewSet.list
POST   /api/v1/users/                  UserViewSet.create
GET    /api/v1/users/<id>/             UserViewSet.retrieve
PATCH  /api/v1/users/<id>/             UserViewSet.partial_update
DELETE /api/v1/users/<id>/             UserViewSet.destroy  (soft-deactivate)
POST   /api/v1/users/<id>/unlock/      UserViewSet.unlock
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django_filters.rest_framework import DjangoFilterBackend

from .models import Role
from .permissions import IsAdmin, IsAnyStaff, IsOwnUserAccount
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserSerializer,
    UserAdminSerializer,
    RegisterUserSerializer,
    ChangePasswordSerializer,
    UnlockUserSerializer,
)
from accounts.signals import write_audit, AuditAction

User = get_user_model()
logger = logging.getLogger("hms.accounts")


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------

class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/
    Returns { access, refresh } JWT pair.
    Throttled to 5 requests/minute per IP (configured in settings).
    """
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope   = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Write audit on successful login
            try:
                email = request.data.get("email", "").lower()
                user  = User.objects.get(email=email)
                write_audit(
                    action=AuditAction.LOGIN,
                    table_name="accounts_user",
                    record_id=user.pk,
                    user=user,
                )
            except Exception:
                pass  # never fail a login over an audit write error
        return response


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Blacklists the refresh token, effectively invalidating the session.
    The access token expires naturally (15 min TTL).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            write_audit(
                action=AuditAction.LOGOUT,
                table_name="accounts_user",
                record_id=request.user.pk,
                user=request.user,
            )
            logger.info("User %s logged out", request.user.email)
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.warning("Logout failed: %s", exc)
            return Response({"error": "Invalid or already blacklisted token."}, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    """
    GET   /api/v1/auth/me/    → returns current user's profile
    PATCH /api/v1/auth/me/    → updates non-security fields (name not stored on User,
                                but role/is_active update allowed for admins)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer_class = UserAdminSerializer if request.user.is_admin else UserSerializer
        serializer = serializer_class(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        serializer_class = UserAdminSerializer if request.user.is_admin else UserSerializer
        serializer = serializer_class(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/me/password/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        write_audit(
            action=AuditAction.UPDATE,
            table_name="accounts_user",
            record_id=request.user.pk,
            user=request.user,
            new_value={"action": "password_changed"},
        )
        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# User management viewset (admin-only)
# ---------------------------------------------------------------------------

class UserViewSet(viewsets.ModelViewSet):
    """
    Admin-managed user accounts.

    list            GET    /users/
    create          POST   /users/
    retrieve        GET    /users/<id>/
    partial_update  PATCH  /users/<id>/
    destroy         DELETE /users/<id>/     → soft-deactivate (never hard delete)
    unlock          POST   /users/<id>/unlock/
    """
    queryset = User.objects.all().order_by("email")
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["role", "is_active", "mfa_enabled"]
    search_fields    = ["email"]
    ordering_fields  = ["email", "created_at", "role"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("retrieve",):
            # Users can retrieve their own profile; admins can retrieve any
            return [IsOwnUserAccount()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == "create":
            return RegisterUserSerializer
        return UserAdminSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Non-admin users should only see themselves (belt-and-suspenders)
        if not self.request.user.is_admin:
            qs = qs.filter(pk=self.request.user.pk)
        return qs

    def perform_destroy(self, instance):
        """Soft-deactivate instead of hard delete."""
        if instance.pk == self.request.user.pk:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("You cannot deactivate your own account.")
        instance.deactivate()
        write_audit(
            action=AuditAction.UPDATE,
            table_name="accounts_user",
            record_id=instance.pk,
            user=self.request.user,
            new_value={"is_active": False, "action": "deactivated"},
        )

    @action(detail=True, methods=["post"], url_path="unlock")
    def unlock(self, request, pk=None):
        """POST /users/<id>/unlock/  — clear lockout state."""
        user = self.get_object()
        serializer = UnlockUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_count", "locked_until", "updated_at"])
        write_audit(
            action=AuditAction.UPDATE,
            table_name="accounts_user",
            record_id=user.pk,
            user=request.user,
            new_value={"action": "account_unlocked", "reason": serializer.validated_data.get("reason", "")},
        )
        return Response({"detail": f"Account {user.email} has been unlocked."})

    @action(detail=False, methods=["get"], url_path="roles")
    def roles(self, request):
        """GET /users/roles/  — list valid role choices."""
        return Response([{"value": r.value, "label": r.label} for r in Role])
