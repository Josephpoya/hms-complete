from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ("email", "role", "is_active", "mfa_enabled", "created_at")
    list_filter   = ("role", "is_active", "mfa_enabled")
    search_fields = ("email",)
    ordering      = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at", "last_login")

    fieldsets = (
        (None,          {"fields": ("id", "email", "password")}),
        ("Role",        {"fields": ("role",)}),
        ("Status",      {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("MFA",         {"fields": ("mfa_enabled", "mfa_secret")}),
        ("Security",    {"fields": ("failed_login_count", "locked_until")}),
        ("Timestamps",  {"fields": ("created_at", "updated_at", "last_login")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "role", "password1", "password2"),
        }),
    )
