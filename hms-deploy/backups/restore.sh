#!/usr/bin/env bash
# =============================================================================
# HMS Database Restore Script
# Usage: bash restore.sh /var/backups/hms/database/hms_db_2024-01-15_02-00-00.sql.gz
#
# WARNING: This DROPS and recreates the hms_db database.
#          Run only during a maintenance window.
# =============================================================================
set -euo pipefail

DUMP_FILE="${1:?Usage: $0 <path-to-dump.sql.gz>}"
DB_NAME="hms_db"
DB_USER="hms_user"

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

[ -f "$DUMP_FILE" ] || die "Dump file not found: $DUMP_FILE"

log "=== HMS DATABASE RESTORE ==="
log "Source:   $DUMP_FILE"
log "Database: $DB_NAME"
log ""
read -r -p "This will DESTROY all current data in $DB_NAME. Type 'yes' to continue: " CONFIRM
[ "$CONFIRM" = "yes" ] || die "Aborted."

# Stop application services
log "Stopping application services..."
systemctl stop hms-gunicorn hms-celery hms-celerybeat 2>/dev/null || true

# Drop and recreate database
log "Recreating database..."
sudo -u postgres psql << SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS $DB_NAME;
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
SQL

# Restore
log "Restoring from dump..."
sudo -u postgres pg_restore \
    --dbname="$DB_NAME" \
    --no-owner \
    --no-acl \
    --verbose \
    "$DUMP_FILE" 2>&1 | tail -20

# Run any pending migrations
log "Applying migrations..."
source /etc/hms/.env
DJANGO_SETTINGS_MODULE=config.settings.production \
/var/www/hms/venv/bin/python /var/www/hms/manage.py migrate --noinput

# Restart services
log "Restarting services..."
systemctl start hms-gunicorn hms-celery hms-celerybeat

log "✅ Restore complete. Verify the application at https://yourdomain.com/health/"
