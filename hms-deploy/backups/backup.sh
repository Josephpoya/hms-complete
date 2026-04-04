#!/usr/bin/env bash
# =============================================================================
# HMS Backup Script
# Cron: 0 2 * * * /etc/hms/backup.sh >> /var/log/hms/backup.log 2>&1
#
# What it backs up:
#   1. PostgreSQL — full dump (compressed)
#   2. Environment file
#   3. Application media (if not using S3)
#   4. Uploads to S3 (if configured)
#   5. Prunes local backups older than KEEP_DAYS
# =============================================================================
set -euo pipefail

BACKUP_DIR="/var/backups/hms"
KEEP_DAYS=7
DATE=$(date '+%Y-%m-%d_%H-%M-%S')
DB_NAME="hms_db"
DB_USER="hms_user"
S3_BUCKET="${AWS_STORAGE_BUCKET_NAME:-}"
S3_PREFIX="database-backups"

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fail() { echo "[BACKUP FAILED] $*" >&2; exit 1; }

# Load environment
[ -f /etc/hms/.env ] && source /etc/hms/.env

mkdir -p "$BACKUP_DIR"/{database,env,media,wal}
log "Starting HMS backup — $DATE"

# ─── 1. PostgreSQL dump ───────────────────────────────────────────────────────
DUMP_FILE="$BACKUP_DIR/database/hms_db_${DATE}.sql.gz"
log "Dumping PostgreSQL database..."
sudo -u postgres pg_dump \
    --format=custom \
    --compress=9 \
    --no-password \
    --file="$DUMP_FILE" \
    "$DB_NAME" || fail "pg_dump failed"

DUMP_SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
log "Database dump: $DUMP_FILE ($DUMP_SIZE)"

# Verify the dump is readable
sudo -u postgres pg_restore --list "$DUMP_FILE" > /dev/null || fail "pg_restore verification failed"
log "Dump verification: OK"

# ─── 2. Environment file ──────────────────────────────────────────────────────
cp /etc/hms/.env "$BACKUP_DIR/env/env_${DATE}.env"
chmod 600 "$BACKUP_DIR/env/env_${DATE}.env"

# ─── 3. Application media (if local) ─────────────────────────────────────────
MEDIA_DIR="/var/www/hms/media"
if [ -d "$MEDIA_DIR" ] && [ -n "$(ls -A $MEDIA_DIR 2>/dev/null)" ]; then
    MEDIA_FILE="$BACKUP_DIR/media/media_${DATE}.tar.gz"
    tar -czf "$MEDIA_FILE" -C "$MEDIA_DIR" . 2>/dev/null || true
    log "Media backup: $MEDIA_FILE"
fi

# ─── 4. Upload to S3 ─────────────────────────────────────────────────────────
if [ -n "$S3_BUCKET" ] && command -v aws &>/dev/null; then
    log "Uploading backup to S3 s3://$S3_BUCKET/$S3_PREFIX/ ..."
    aws s3 cp "$DUMP_FILE" "s3://$S3_BUCKET/$S3_PREFIX/$(basename $DUMP_FILE)" \
        --storage-class STANDARD_IA \
        --sse AES256 \
        || log "WARNING: S3 upload failed — local backup is still intact"
    log "S3 upload complete"
fi

# ─── 5. Prune old local backups ───────────────────────────────────────────────
log "Pruning backups older than $KEEP_DAYS days..."
find "$BACKUP_DIR/database" -name "*.sql.gz" -mtime +$KEEP_DAYS -delete
find "$BACKUP_DIR/env"      -name "*.env"    -mtime +$KEEP_DAYS -delete
find "$BACKUP_DIR/media"    -name "*.tar.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null || true

# ─── 6. Report disk usage ─────────────────────────────────────────────────────
TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Backup complete. Total backup size: $TOTAL"
log "Latest backup: $DUMP_FILE ($DUMP_SIZE)"
