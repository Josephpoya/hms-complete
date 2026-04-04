"""
Initial migration for accounts app.
Creates the custom User table and AuditLog table.
Also creates the PostgreSQL sequences used for MRN and Invoice numbers.
"""
import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        # Sequences for human-readable IDs (used by Patient.mrn and Invoice.invoice_number)
        migrations.RunSQL(
            sql="CREATE SEQUENCE IF NOT EXISTS patients_mrn_seq START 1;",
            reverse_sql="DROP SEQUENCE IF EXISTS patients_mrn_seq;",
        ),
        migrations.RunSQL(
            sql="CREATE SEQUENCE IF NOT EXISTS billing_invoice_seq START 1;",
            reverse_sql="DROP SEQUENCE IF EXISTS billing_invoice_seq;",
        ),

        migrations.CreateModel(
            name="User",
            fields=[
                ("id",                  models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ("password",            models.CharField(max_length=128, verbose_name="password")),
                ("email",               models.EmailField(max_length=255, unique=True)),
                ("role",                models.CharField(max_length=30, choices=[
                    ("admin","Admin"),("doctor","Doctor"),("nurse","Nurse"),("receptionist","Receptionist")
                ])),
                ("is_active",           models.BooleanField(default=True)),
                ("is_staff",            models.BooleanField(default=False)),
                ("is_superuser",        models.BooleanField(default=False)),
                ("mfa_enabled",         models.BooleanField(default=False)),
                ("mfa_secret",          models.CharField(max_length=64, blank=True, null=True)),
                ("failed_login_count",  models.PositiveSmallIntegerField(default=0)),
                ("locked_until",        models.DateTimeField(null=True, blank=True)),
                ("created_at",          models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at",          models.DateTimeField(auto_now=True)),
                ("last_login",          models.DateTimeField(null=True, blank=True)),
            ],
            options={"db_table": "accounts_user"},
        ),

        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id",                  models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ("user",                models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                            related_name="audit_logs", to=settings.AUTH_USER_MODEL)),
                ("user_email_snapshot", models.CharField(max_length=255)),
                ("user_role_snapshot",  models.CharField(max_length=30)),
                ("action",              models.CharField(max_length=20)),
                ("table_name",          models.CharField(max_length=80)),
                ("record_id",           models.UUIDField(null=True, blank=True)),
                ("old_value",           models.JSONField(null=True, blank=True)),
                ("new_value",           models.JSONField(null=True, blank=True)),
                ("ip_address",          models.GenericIPAddressField(null=True, blank=True)),
                ("user_agent",          models.TextField(blank=True)),
                ("created_at",          models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ],
            options={"db_table": "audit_auditlog", "ordering": ["-created_at"]},
        ),

        # Indexes
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["email"], name="idx_user_email"),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["role"], name="idx_user_role"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["action"], name="idx_audit_action"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["table_name"], name="idx_audit_table"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["created_at"], name="idx_audit_created"),
        ),

        # Revoke DELETE/UPDATE on audit_auditlog from the app DB user
        # (Run after creating table — requires superuser during migration)
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'hms_user') THEN
                        REVOKE UPDATE, DELETE ON audit_auditlog FROM hms_user;
                    END IF;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
