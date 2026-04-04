"""
Celery application instance.
Import this in config/__init__.py so tasks are auto-discovered.
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("hms")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
