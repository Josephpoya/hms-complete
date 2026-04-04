# =============================================================================
# HMS Django Application Dockerfile
# Multi-stage build — development and production targets
# =============================================================================

# ── Stage 1: Python base ─────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS base

# Prevent Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent Python from buffering stdout/stderr (important for log capture)
ENV PYTHONUNBUFFERED=1
# Force UTF-8
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

WORKDIR /var/www/hms

# Install OS-level dependencies
# libpq-dev   — PostgreSQL client library for psycopg2
# gettext     — Django's makemessages/compilemessages
# curl        — health check in docker-compose
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    gettext \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies in a separate layer (cache-friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel \
 && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Development ─────────────────────────────────────────────────────
FROM base AS development

# Install dev extras
RUN pip install --no-cache-dir \
    django-debug-toolbar \
    pytest-django \
    factory-boy \
    black \
    flake8

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


# ── Stage 3: Production ──────────────────────────────────────────────────────
FROM base AS production

# Create non-root user to run the application
# UID 1001 avoids conflict with common system UIDs
RUN groupadd --gid 1001 hms \
 && useradd  --uid 1001 --gid hms --shell /bin/bash --no-create-home hms

# Copy application code
COPY --chown=hms:hms . .

# Create required directories
RUN mkdir -p /var/www/hms/staticfiles \
             /var/www/hms/media \
             /var/log/hms \
 && chown -R hms:hms /var/www/hms /var/log/hms

# Switch to non-root user
USER hms

# Collect static files at build time
# (requires DJANGO_SETTINGS_MODULE env — set as ARG for build-time only)
ARG DJANGO_SETTINGS_MODULE=config.settings.production
ARG SECRET_KEY=build-time-dummy-key-not-for-production
ARG DATABASE_URL=postgres://dummy/dummy

RUN DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE \
    SECRET_KEY=$SECRET_KEY \
    DATABASE_URL=$DATABASE_URL \
    python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

# Gunicorn:
#   --workers        = (2 × CPU) + 1 per replica; adjust via GUNICORN_WORKERS env
#   --worker-class   = gthread for I/O-bound Django (each thread handles one request)
#   --max-requests   = recycle workers periodically to prevent memory creep
#   --worker-tmp-dir = /dev/shm prevents disk I/O for heartbeat files
CMD ["sh", "-c", \
    "gunicorn config.wsgi:application \
     --bind 0.0.0.0:8000 \
     --workers ${GUNICORN_WORKERS:-4} \
     --threads ${GUNICORN_THREADS:-2} \
     --worker-class gthread \
     --worker-tmp-dir /dev/shm \
     --timeout 30 \
     --graceful-timeout 10 \
     --max-requests 1000 \
     --max-requests-jitter 100 \
     --log-level warning \
     --access-logfile - \
     --error-logfile -" \
]
