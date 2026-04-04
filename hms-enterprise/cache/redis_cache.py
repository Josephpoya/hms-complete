"""
cache/redis_cache.py
====================
Enterprise Redis caching layer for HMS.

Design principles
-----------------
1. Every cache key is namespaced (hms:<version>:<resource>:<id>)
   so cache invalidation is surgical and version-bumping clears all old keys.

2. Cache-aside pattern: read from cache → miss → read from DB → write cache.
   The Django ORM call is never bypassed; caching wraps it.

3. Invalidation on write: signal handlers clear the cache key for any
   model instance that is saved or deleted.

4. TTLs are conservative for clinical data (short) and liberal for
   reference data like drug catalogues (long).

Cached resources
----------------
  Patient list         TTL  5 min  — list queries per page/filter combo
  Patient detail       TTL 10 min  — single patient demographics
  Doctor list          TTL 30 min  — doctor directory changes rarely
  Drug catalogue       TTL 60 min  — drug prices and stock
  Appointment today    TTL  2 min  — dashboard "today" list, refreshes often
  Dashboard stats      TTL  5 min  — KPI aggregates

Usage
-----
  from cache.redis_cache import PatientCache, AppointmentCache

  # In a view or serializer:
  patients = PatientCache.get_list(page=1, search="Okello")
  if patients is None:
      patients = _fetch_from_db(...)
      PatientCache.set_list(patients, page=1, search="Okello")
"""

import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable, Optional

from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger("hms.cache")

# ─── Cache version — bump this to instantly invalidate ALL hms cache keys ─────
CACHE_VERSION = getattr(settings, "HMS_CACHE_VERSION", "v1")


# ─── TTL constants ────────────────────────────────────────────────────────────
class TTL:
    VERY_SHORT =    60        #  1 minute  — live counters
    SHORT      =   300        #  5 minutes — appointment today list
    MEDIUM     =   600        # 10 minutes — patient detail
    LONG       =  1800        # 30 minutes — doctor directory
    VERY_LONG  =  3600        # 60 minutes — drug catalogue, settings
    DAILY      = 86400        # 24 hours   — static reference data


# ─── Key builder ──────────────────────────────────────────────────────────────
def _make_key(*parts: str) -> str:
    """Build a namespaced, version-tagged cache key."""
    raw = ":".join(["hms", CACHE_VERSION, *[str(p) for p in parts]])
    # Hash long keys (filter strings can be very long)
    if len(raw) > 200:
        hashed = hashlib.sha256(raw.encode()).hexdigest()[:16]
        raw = f"hms:{CACHE_VERSION}:h:{hashed}"
    return raw


def _filter_hash(**kwargs) -> str:
    """Stable hash of a filter dict for use in cache keys."""
    return hashlib.md5(
        json.dumps(kwargs, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]


# ─── Patient cache ────────────────────────────────────────────────────────────
class PatientCache:
    PREFIX = "patient"

    @classmethod
    def detail_key(cls, patient_id: str) -> str:
        return _make_key(cls.PREFIX, "detail", patient_id)

    @classmethod
    def list_key(cls, **filters) -> str:
        return _make_key(cls.PREFIX, "list", _filter_hash(**filters))

    @classmethod
    def get_detail(cls, patient_id: str) -> Optional[dict]:
        return cache.get(cls.detail_key(patient_id))

    @classmethod
    def set_detail(cls, patient_id: str, data: dict) -> None:
        cache.set(cls.detail_key(patient_id), data, TTL.MEDIUM)
        logger.debug("cache set: patient detail %s", patient_id)

    @classmethod
    def get_list(cls, **filters) -> Optional[dict]:
        return cache.get(cls.list_key(**filters))

    @classmethod
    def set_list(cls, data: dict, **filters) -> None:
        cache.set(cls.list_key(**filters), data, TTL.SHORT)

    @classmethod
    def invalidate(cls, patient_id: str) -> None:
        """Called by signal on Patient save/delete."""
        cache.delete(cls.detail_key(patient_id))
        # Pattern delete for list keys — delete_pattern requires django-redis
        try:
            from django_redis import get_redis_connection
            r = get_redis_connection("default")
            pattern = _make_key(cls.PREFIX, "list", "*")
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
                logger.debug("cache invalidated: %d patient list keys", len(keys))
        except Exception:
            # Fallback: just delete the detail key (lists expire on TTL)
            pass


# ─── Doctor cache ─────────────────────────────────────────────────────────────
class DoctorCache:
    PREFIX = "doctor"

    @classmethod
    def list_key(cls, **filters) -> str:
        return _make_key(cls.PREFIX, "list", _filter_hash(**filters))

    @classmethod
    def workload_key(cls) -> str:
        return _make_key(cls.PREFIX, "workload")

    @classmethod
    def get_list(cls, **filters) -> Optional[dict]:
        return cache.get(cls.list_key(**filters))

    @classmethod
    def set_list(cls, data: dict, **filters) -> None:
        cache.set(cls.list_key(**filters), data, TTL.LONG)

    @classmethod
    def get_workload(cls) -> Optional[list]:
        return cache.get(cls.workload_key())

    @classmethod
    def set_workload(cls, data: list) -> None:
        # Workload (today's counts) changes every appointment — short TTL
        cache.set(cls.workload_key(), data, TTL.VERY_SHORT)

    @classmethod
    def invalidate_workload(cls) -> None:
        cache.delete(cls.workload_key())


# ─── Appointment cache ────────────────────────────────────────────────────────
class AppointmentCache:
    PREFIX = "appointment"

    @classmethod
    def today_key(cls, user_id: Optional[str] = None) -> str:
        scope = user_id or "all"
        return _make_key(cls.PREFIX, "today", scope)

    @classmethod
    def get_today(cls, user_id: Optional[str] = None) -> Optional[list]:
        return cache.get(cls.today_key(user_id))

    @classmethod
    def set_today(cls, data: list, user_id: Optional[str] = None) -> None:
        cache.set(cls.today_key(user_id), data, TTL.VERY_SHORT)

    @classmethod
    def invalidate_today(cls) -> None:
        """Invalidate all 'today' keys — called when any appointment changes."""
        try:
            from django_redis import get_redis_connection
            r = get_redis_connection("default")
            pattern = _make_key(cls.PREFIX, "today", "*")
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
        except Exception:
            cache.delete(cls.today_key())


# ─── Drug catalogue cache ─────────────────────────────────────────────────────
class DrugCache:
    PREFIX = "drug"

    @classmethod
    def catalogue_key(cls, **filters) -> str:
        return _make_key(cls.PREFIX, "catalogue", _filter_hash(**filters))

    @classmethod
    def low_stock_key(cls) -> str:
        return _make_key(cls.PREFIX, "low_stock")

    @classmethod
    def get_catalogue(cls, **filters) -> Optional[dict]:
        return cache.get(cls.catalogue_key(**filters))

    @classmethod
    def set_catalogue(cls, data: dict, **filters) -> None:
        cache.set(cls.catalogue_key(**filters), data, TTL.VERY_LONG)

    @classmethod
    def get_low_stock(cls) -> Optional[dict]:
        return cache.get(cls.low_stock_key())

    @classmethod
    def set_low_stock(cls, data: dict) -> None:
        cache.set(cls.low_stock_key(), data, TTL.SHORT)

    @classmethod
    def invalidate(cls, drug_id: Optional[str] = None) -> None:
        cache.delete(cls.low_stock_key())
        try:
            from django_redis import get_redis_connection
            r = get_redis_connection("default")
            pattern = _make_key(cls.PREFIX, "catalogue", "*")
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
        except Exception:
            pass


# ─── Dashboard stats cache ────────────────────────────────────────────────────
class DashboardCache:
    PREFIX = "dashboard"

    @classmethod
    def stats_key(cls, role: str) -> str:
        return _make_key(cls.PREFIX, "stats", role)

    @classmethod
    def get_stats(cls, role: str) -> Optional[dict]:
        return cache.get(cls.stats_key(role))

    @classmethod
    def set_stats(cls, data: dict, role: str) -> None:
        cache.set(cls.stats_key(role), data, TTL.SHORT)

    @classmethod
    def invalidate_all(cls) -> None:
        for role in ("admin", "doctor", "nurse", "receptionist"):
            cache.delete(cls.stats_key(role))


# ─── Generic cache decorator ──────────────────────────────────────────────────
def cached(ttl: int = TTL.MEDIUM, key_fn: Optional[Callable] = None):
    """
    Decorator for caching view or service method results.

    Usage
    -----
    @cached(ttl=TTL.LONG, key_fn=lambda self, pk: f"mymodel:{pk}")
    def get_object(self, pk):
        return MyModel.objects.get(pk=pk)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache_key = (
                key_fn(*args, **kwargs)
                if key_fn
                else _make_key(func.__module__, func.__name__, *map(str, args))
            )
            hit = cache.get(cache_key)
            if hit is not None:
                logger.debug("cache hit: %s", cache_key)
                return hit
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            logger.debug("cache miss → set: %s (ttl=%ds)", cache_key, ttl)
            return result
        return wrapper
    return decorator


# ─── Signal-based cache invalidation ─────────────────────────────────────────
def register_cache_invalidation_signals():
    """
    Register Django signals to automatically invalidate cache entries
    when model data changes. Call from AppConfig.ready().
    """
    from django.db.models.signals import post_save, post_delete
    from django.apps import apps

    def _invalidate_patient(sender, instance, **kwargs):
        PatientCache.invalidate(str(instance.pk))
        DashboardCache.invalidate_all()

    def _invalidate_appointment(sender, instance, **kwargs):
        AppointmentCache.invalidate_today()
        DoctorCache.invalidate_workload()
        DashboardCache.invalidate_all()

    def _invalidate_drug(sender, instance, **kwargs):
        DrugCache.invalidate(str(instance.pk))

    try:
        Patient     = apps.get_model("patients", "Patient")
        Appointment = apps.get_model("appointments", "Appointment")
        Drug        = apps.get_model("pharmacy", "Drug")

        post_save.connect(_invalidate_patient,     sender=Patient,     weak=False, dispatch_uid="cache_patient_save")
        post_delete.connect(_invalidate_patient,   sender=Patient,     weak=False, dispatch_uid="cache_patient_delete")
        post_save.connect(_invalidate_appointment, sender=Appointment, weak=False, dispatch_uid="cache_appt_save")
        post_save.connect(_invalidate_drug,        sender=Drug,        weak=False, dispatch_uid="cache_drug_save")
    except LookupError as e:
        logger.warning("Cache signal registration skipped: %s", e)
