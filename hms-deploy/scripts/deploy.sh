#!/usr/bin/env bash
# =============================================================================
# HMS Application Deployment Script
# Runs as the hms user or with sudo.
# Usage: bash deploy.sh [--branch main] [--skip-migrate]
# =============================================================================
set -euo pipefail

APP_DIR="/var/www/hms"
REPO_URL="${HMS_REPO_URL:-https://github.com/yourorg/hms.git}"
BRANCH="main"
SKIP_MIGRATE=false
VENV="$APP_DIR/venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --branch) BRANCH="$2"; shift 2 ;;
        --skip-migrate) SKIP_MIGRATE=true; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

# ─── Pre-flight checks ────────────────────────────────────────────────────────
log "Starting HMS deployment (branch: $BRANCH)"
[ -f /etc/hms/.env ] || die "/etc/hms/.env not found. Copy and configure .env.production first."
source /etc/hms/.env

# ─── Code update ─────────────────────────────────────────────────────────────
log "Updating code..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ─── Python environment ───────────────────────────────────────────────────────
log "Updating Python environment..."
if [ ! -d "$VENV" ]; then
    python3.11 -m venv "$VENV"
fi
"$PIP" install --quiet --upgrade pip wheel
"$PIP" install --quiet -r requirements.txt

# ─── Database migrations ─────────────────────────────────────────────────────
if [ "$SKIP_MIGRATE" = false ]; then
    log "Running database migrations..."
    DJANGO_SETTINGS_MODULE=config.settings.production \
    "$PYTHON" manage.py migrate --noinput
fi

# ─── Static files ─────────────────────────────────────────────────────────────
log "Collecting static files..."
DJANGO_SETTINGS_MODULE=config.settings.production \
"$PYTHON" manage.py collectstatic --noinput --clear \
    --settings=config.settings.production

# ─── Django system checks ─────────────────────────────────────────────────────
log "Running system checks..."
DJANGO_SETTINGS_MODULE=config.settings.production \
"$PYTHON" manage.py check --deploy 2>&1 | grep -v "^System check" || true

# ─── Celery Beat schedule update ─────────────────────────────────────────────
log "Setting up periodic task schedules..."
DJANGO_SETTINGS_MODULE=config.settings.production \
"$PYTHON" manage.py shell -c "
from core.apps import CoreConfig
app = CoreConfig('core', None)
app._register_celery_beat_schedule()
print('Periodic tasks registered.')
" 2>/dev/null || true

# ─── Restart services (zero-downtime) ─────────────────────────────────────────
log "Reloading services..."
sudo systemctl reload hms-gunicorn  2>/dev/null || sudo systemctl restart hms-gunicorn
sudo systemctl restart hms-celery
sudo systemctl restart hms-celerybeat

# ─── Smoke test ───────────────────────────────────────────────────────────────
log "Smoke test..."
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    log "✅ Deployment successful. Health check: HTTP $HTTP_CODE"
else
    die "Health check returned HTTP $HTTP_CODE — deployment may have failed. Check: journalctl -u hms-gunicorn -n 50"
fi

log "Deployment complete."
