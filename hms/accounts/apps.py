from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Signal registration moved to core/apps.py to avoid circular imports.
        # accounts/signals.py still provides backwards-compatible write_audit()
        pass
