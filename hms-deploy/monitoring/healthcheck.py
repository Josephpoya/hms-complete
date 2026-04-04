#!/usr/bin/env python3
"""
HMS Health Check Endpoint
=========================
Adds a lightweight /health/ endpoint to Django.
Add to config/urls.py:  path('health/', include('monitoring.healthcheck'))

Or drop this file anywhere and add to urls.py:
    from monitoring.healthcheck import health_view
    path('health/', health_view)
"""

import json
import time
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def health_view(request):
    """
    GET /health/
    Returns 200 if all critical services are reachable.
    Returns 503 if any critical check fails.

    Checks:
    - Database connectivity and query latency
    - Cache (Redis) connectivity
    - Disk space (basic threshold)
    """
    checks = {}
    overall = "healthy"
    start   = time.monotonic()

    # ─── Database ─────────────────────────────────────────────────────────────
    try:
        db_start = time.monotonic()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_ms = round((time.monotonic() - db_start) * 1000, 2)
        checks["database"] = {"status": "ok", "latency_ms": db_ms}
        if db_ms > 500:
            checks["database"]["warning"] = "High latency"
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
        overall = "unhealthy"

    # ─── Cache (Redis) ────────────────────────────────────────────────────────
    try:
        cache_start = time.monotonic()
        cache.set("hms_healthcheck", "ok", timeout=10)
        result = cache.get("hms_healthcheck")
        cache_ms = round((time.monotonic() - cache_start) * 1000, 2)
        if result == "ok":
            checks["cache"] = {"status": "ok", "latency_ms": cache_ms}
        else:
            checks["cache"] = {"status": "error", "error": "Cache read/write mismatch"}
            overall = "unhealthy"
    except Exception as e:
        checks["cache"] = {"status": "error", "error": str(e)}
        overall = "unhealthy"

    # ─── Disk space ───────────────────────────────────────────────────────────
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        pct_used = round((used / total) * 100, 1)
        checks["disk"] = {
            "status":   "warning" if pct_used > 85 else "ok",
            "pct_used": pct_used,
            "free_gb":  round(free / (1024 ** 3), 2),
        }
        if pct_used > 90:
            overall = "degraded"
    except Exception as e:
        checks["disk"] = {"status": "error", "error": str(e)}

    total_ms = round((time.monotonic() - start) * 1000, 2)

    payload = {
        "status":       overall,
        "total_ms":     total_ms,
        "checks":       checks,
        "version":      "1.0.0",
    }

    status_code = 200 if overall == "healthy" else 503
    return JsonResponse(payload, status=status_code)
