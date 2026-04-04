"""
accounts/permissions.py
=======================
All custom DRF permission classes for the HMS.

Architecture
------------
Permission classes are composable — views use them individually or combine
them with DRF's `|` / `&` operators (DRF 3.14+), or by listing multiple
classes in `permission_classes` (AND semantics).

Object-level permissions
------------------------
has_object_permission() is the second gate — called only after
has_permission() returns True. Always call check_object_permissions()
in retrieve/update/destroy before returning data.

Pattern used in viewsets
------------------------
get_permissions() returns different permission class instances based on
the action name (list, create, retrieve, update, partial_update, destroy,
plus any custom @action names). This gives per-action RBAC without
duplicating logic across separate APIView subclasses.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import Role


# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------

def _authenticated(request):
    return bool(request.user and request.user.is_authenticated)


def _role_in(request, *roles):
    return _authenticated(request) and request.user.role in roles


# ---------------------------------------------------------------------------
# Role-level permissions (view-gate only)
# ---------------------------------------------------------------------------

class IsAdmin(BasePermission):
    """Full system access. Only the admin role."""
    message = "You must be an administrator to perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.ADMIN)


class IsDoctor(BasePermission):
    """Doctors only."""
    message = "Only doctors can perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.DOCTOR)


class IsNurse(BasePermission):
    """Nurses only."""
    message = "Only nurses can perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.NURSE)


class IsReceptionist(BasePermission):
    """Receptionists only."""
    message = "Only receptionists can perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.RECEPTIONIST)


# ---------------------------------------------------------------------------
# Composite role permissions
# ---------------------------------------------------------------------------

class IsAdminOrDoctor(BasePermission):
    message = "Only administrators or doctors can perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.ADMIN, Role.DOCTOR)


class IsAdminOrNurse(BasePermission):
    message = "Only administrators or nurses can perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.ADMIN, Role.NURSE)


class IsAdminOrReceptionist(BasePermission):
    message = "Only administrators or receptionists can perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.ADMIN, Role.RECEPTIONIST)


class IsClinicalStaff(BasePermission):
    """Doctors, nurses, and admins — anyone with direct patient contact."""
    message = "Only clinical staff (doctors, nurses, admins) can perform this action."

    def has_permission(self, request, view):
        return _role_in(request, Role.ADMIN, Role.DOCTOR, Role.NURSE)


class IsAnyStaff(BasePermission):
    """Any authenticated user with a valid HMS role."""
    message = "Authentication required."

    def has_permission(self, request, view):
        return _authenticated(request)


# ---------------------------------------------------------------------------
# HTTP-method-based permissions
# ---------------------------------------------------------------------------

class IsAuthenticatedReadOnly(BasePermission):
    """Authenticated users may read; write requires admin."""
    message = "Write access requires administrator privileges."

    def has_permission(self, request, view):
        if not _authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_admin


# ---------------------------------------------------------------------------
# Object-level permissions
# ---------------------------------------------------------------------------

class IsDoctorOwner(BasePermission):
    """
    Object-level: doctor can only access records they authored.
    Admins bypass this check.
    Used on MedicalRecord, Prescription detail views.
    """
    message = "You can only access records you authored."

    def has_permission(self, request, view):
        return _role_in(request, Role.ADMIN, Role.DOCTOR, Role.NURSE)

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin or request.user.is_nurse:
            return True
        # Safe methods: all clinical staff can read
        if request.method in SAFE_METHODS:
            return True
        # Write: only the authoring doctor
        if request.user.is_doctor:
            doctor_profile = getattr(request.user, "doctor_profile", None)
            if not doctor_profile:
                return False
            # obj could be a MedicalRecord or Prescription
            author_id = getattr(obj, "doctor_id", None)
            return str(author_id) == str(doctor_profile.id)
        return False


class IsPatientDataOwner(BasePermission):
    """
    Object-level: receptionists and admins can edit any patient;
    doctors/nurses can read but not edit demographics.
    """
    message = "You do not have permission to modify this patient's record."

    def has_permission(self, request, view):
        return _authenticated(request)

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin:
            return True
        if request.method in SAFE_METHODS:
            # All authenticated staff can read patient demographics
            return True
        # Only admin and receptionist can write patient data
        return request.user.is_receptionist


class IsInvoiceOwner(BasePermission):
    """
    Object-level: admins and receptionists can manage invoices;
    clinical staff can read only.
    """
    message = "Only administrators and receptionists can modify invoices."

    def has_permission(self, request, view):
        return _authenticated(request)

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin:
            return True
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_receptionist


class IsOwnUserAccount(BasePermission):
    """
    Object-level: users can only modify their own account.
    Admins can modify any account.
    """
    message = "You can only modify your own account."

    def has_permission(self, request, view):
        return _authenticated(request)

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin:
            return True
        return obj.pk == request.user.pk
