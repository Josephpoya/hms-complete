# HMS Enterprise Upgrade Guide

This guide explains each enterprise addition, why it was chosen, and how
to apply it to the existing HMS codebase.

---

## 1. Docker

**What:** A full multi-container Docker stack (PostgreSQL, Redis, PgBouncer,
Django/Gunicorn, Celery, Nginx) orchestrated by Docker Compose.

**Why:** Docker makes the environment reproducible. Every developer, CI runner,
and production server runs identical software versions. Containers are isolated —
a crash in Celery doesn't affect the Gunicorn process. Scaling is a single command.

**Key decisions:**
- **Multi-stage Dockerfile** (`base → development → production`): production images
  don't include dev tools (pytest, debug toolbar). Smaller images = faster pulls = less attack surface.
- **PgBouncer** sits between the app and PostgreSQL. Each Gunicorn thread holds
  a "connection" to PgBouncer, not to Postgres. PgBouncer pools these into
  5–20 actual Postgres connections. Without it, 4 workers × 2 threads = 8 connections
  — fine at small scale. At 10 replicas × 4 workers × 2 threads = 80 connections,
  which eats Postgres's `max_connections` budget fast.
- **`transaction` pool mode** on PgBouncer: connections are released to the pool
  at the end of each transaction (not session). This is correct for Django because
  each view runs in one transaction.
- **Celery Beat runs exactly 1 replica.** Running 2 Beat instances would fire every
  periodic task twice. The `deploy.replicas: 1` in compose enforces this.

### Quick start

```bash
cd docker
cp .env.example .env.production
# Fill in .env.production with your values
docker compose --env-file .env.production up -d

# Run migrations inside the app container
docker compose exec app python manage.py migrate
docker compose exec app python manage.py createsuperuser

# Scale Celery workers
docker compose up -d --scale celery=4
```

### Zero-downtime deploy

```bash
# Build new image
docker compose build app

# Rolling restart: one replica at a time (update_config: parallelism=1)
docker compose up -d app
```

---

## 2. Redis Caching

**What:** A strategic cache layer (`cache/redis_cache.py`) with typed cache
classes per resource, automatic invalidation on write, and conservative TTLs for
clinical data.

**Why:** The HMS dashboard makes 5–7 database queries per page load. With Redis
caching those queries for 60–300 seconds, a burst of 50 simultaneous logins at
shift change (7 AM, common in hospitals) produces 5–7 DB queries instead of 250–350.

**Key decisions:**
- **Cache-aside** (not write-through): the application reads from cache first,
  falls back to DB on miss, then stores the result. This is safer for clinical
  data where stale reads must be bounded.
- **Signal-based invalidation**: when a Patient or Appointment is saved, a
  Django post_save signal clears the relevant cache keys immediately. The cache
  never holds stale data beyond one write cycle.
- **Versioned keys** (`hms:v1:patient:list:...`): bumping `HMS_CACHE_VERSION` in
  settings instantly invalidates every HMS cache key without flushing all of Redis.
  This is the correct pattern for schema changes.
- **Short TTLs for clinical data**: appointment lists expire in 2 minutes,
  patient detail in 10 minutes. Drug catalogues (which change only on restock)
  expire in 60 minutes.

### Apply to an existing view

```python
# Before (hits DB every request)
def get_queryset(self):
    return Patient.objects.filter(is_active=True)

# After (cached 5 minutes, invalidated on Patient.save())
from cache.redis_cache import PatientCache

def list(self, request, *args, **kwargs):
    filters = dict(request.query_params)
    cached = PatientCache.get_list(**filters)
    if cached is not None:
        return Response(cached)
    response = super().list(request, *args, **kwargs)
    PatientCache.set_list(response.data, **filters)
    return response
```

### Add django-redis for pattern deletion

```bash
pip install django-redis
```

```python
# settings/base.py
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "PARSER_CLASS":  "redis.connection.HiredisParser",   # faster parser
            "CONNECTION_POOL_KWARGS": {"max_connections": 50},
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",  # compress cached data
        },
        "KEY_PREFIX": "hms",
        "TIMEOUT": 300,
    }
}
```

---

## 3. Celery Background Jobs

**What:** A production-grade Celery configuration with 4 queues, priority routing,
retry logic with exponential backoff, and comprehensive Celery Beat schedules.

**Why:** Any operation that takes more than 200ms should not happen in the HTTP
request cycle. Generating a PDF, sending an SMS, or locking 500 medical records
must be asynchronous. If a worker process crashes mid-task with `acks_late=True`,
the message returns to the queue — the task is never silently lost.

**Queue architecture:**

| Queue | Priority | Workers | Used for |
|-------|----------|---------|----------|
| `critical` | 10 | Dedicated | Medical record locking, security alerts |
| `notifications` | 8 | 4 | SMS, email delivery |
| `default` | 5 | 4 | General async (overdue marks, expiry) |
| `reports` | 3 | 1 | CSV/PDF generation (long-running) |

**Key decisions:**
- **`acks_late=True`**: the broker acknowledges the message only after the task
  function returns successfully. If the worker crashes, the message re-queues.
- **`max-tasks-per-child=200`**: each worker process is recycled after 200 tasks.
  This prevents memory leaks from accumulating over days.
- **Exponential backoff on SMS retry**: `countdown=60 * (2 ** retries)` gives
  60s, 120s, 240s between attempts. This prevents hammering the Africa's Talking
  API during a transient outage.
- **`CELERY_WORKER_PREFETCH_MULTIPLIER=1`**: each worker fetches one task at a
  time. Without this, a worker prefetches several tasks, starving other workers
  that are idle. Critical for fair distribution across queues.

### Add to requirements.txt

```
africastalking==1.5.5
kombu==5.3.4
```

---

## 4. SMS Notifications (Africa's Talking)

**What:** A production SMS service (`notifications/sms_service.py`) with:
- Africa's Talking as the primary provider
- Pluggable provider interface (swap to Twilio by adding a class)
- Message templates as a single source of truth
- Delivery logging to PostgreSQL
- Async dispatch via Celery

**Why Africa's Talking?** They have direct carrier connections to MTN Uganda,
Airtel Uganda, Safaricom Kenya, Vodacom Tanzania. This means higher delivery
rates and lower latency than global SMS aggregators routing through international
gateways.

**Key decisions:**
- **Provider abstraction** (`SMSProvider` ABC): swapping providers in future
  means implementing one class. No view or task code changes.
- **`ConsoleSMSProvider` for development**: SMS is never accidentally sent to real
  patients in dev. The message is printed to stdout instead.
- **Phone normalisation** (`_normalize_phone`): Ugandan numbers entered as
  `0700000000` are automatically converted to `+256700000000` (E.164 format
  required by AT).
- **Delivery log** (`SMSLog`): every message is recorded with the provider's
  message ID, which is used to match incoming delivery receipts from the AT webhook.

### Setup steps

```bash
# 1. Install the package
pip install africastalking

# 2. Register at https://account.africastalking.com
# 3. Create an app and get the API key
# 4. Register a sender ID (alphanumeric like "HMS" — subject to carrier approval)
# 5. Set in .env.production:
AT_API_KEY=your-api-key
AT_USERNAME=your-username
AT_SENDER_ID=HMS
AT_ENVIRONMENT=production
SMS_PROVIDER=africastalking

# 6. Test in sandbox first:
AT_ENVIRONMENT=sandbox
AT_USERNAME=sandbox
```

### Hook notifications into views

```python
# In appointments/views.py — send confirmation after booking
from notifications.tasks import send_appointment_confirmation_task

class AppointmentViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        appt = serializer.save(created_by=self.request.user)
        # Fire-and-forget — doesn't block the HTTP response
        send_appointment_confirmation_task.delay(str(appt.id))
```

---

## 5. Performance Optimisation

**What:** Three levels of optimisation:
1. **Query optimisation** — `select_related`, `prefetch_related`, `.only()` to
   eliminate N+1 queries
2. **Database indexes** — composite and partial indexes targeting actual query patterns
3. **Dashboard aggregation** — single-query CTE replacing 6 separate DB calls

**Why:** Without `select_related`, a list of 25 appointments generates 51 SQL
queries (1 for appointments + 25 for patient + 25 for doctor). With it: 1 query.
At 100 concurrent users, that's the difference between the DB handling 100 or 5,100
queries per page load.

**Key optimisations applied:**

```python
# WRONG — N+1 queries
appointments = Appointment.objects.all()
for a in appointments:
    print(a.patient.full_name)   # SELECT for each patient

# RIGHT — 2 queries total
appointments = Appointment.objects.select_related("patient", "doctor")
```

```sql
-- Partial index: most appointment queries filter by 'booked' status
-- This index is much smaller than a full-table index and fits in RAM
CREATE INDEX idx_appt_doctor_date_active
    ON appointments_appointment (doctor_id, (scheduled_at::date))
    WHERE status NOT IN ('cancelled', 'no_show', 'completed');
```

### Apply performance indexes

```bash
# Run once after deployment
docker compose exec app python manage.py shell -c "
from performance.database_optimisation import apply_performance_indexes
applied = apply_performance_indexes()
print(f'Applied {applied} indexes')
"
```

### Monitor slow queries

```bash
# Find queries running > 500ms in the last 24h
docker compose exec db psql -U hms_user hms_db -c "
SELECT query, calls, mean_exec_time::int AS avg_ms,
       total_exec_time::int AS total_ms, rows
FROM pg_stat_statements
WHERE mean_exec_time > 500
ORDER BY total_exec_time DESC
LIMIT 20;
"
```

---

## Combined requirements additions

Add to `requirements.txt`:

```
# SMS
africastalking==1.5.5

# Redis (faster client)
django-redis==5.4.0
hiredis==2.3.2

# Performance monitoring
django-silk==5.1.0   # Optional: request profiler for development
```
