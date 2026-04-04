#!/usr/bin/env bash
# =============================================================================
# HMS Simple Monitoring & Alert Script
# Cron: */5 * * * * /etc/hms/alert.sh >> /var/log/hms/monitoring.log 2>&1
#
# Checks:
#   - Health endpoint responds 200
#   - Gunicorn process is running
#   - Celery worker is running
#   - Disk usage < 85%
#   - PostgreSQL is accepting connections
#   - SSL certificate expiry > 14 days
#
# Alerts via: email (sendmail) and/or Slack webhook
# =============================================================================
set -euo pipefail

HEALTH_URL="http://localhost/health/"
ALERT_EMAIL="${HMS_ALERT_EMAIL:-admin@yourdomain.com}"
SLACK_WEBHOOK="${HMS_SLACK_WEBHOOK:-}"
DOMAIN="yourdomain.com"
ALERT_SENT_FILE="/tmp/hms_alert_sent"

log()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
alert() {
    local msg="$1"
    log "ALERT: $msg"

    # Throttle: don't send the same alert within 30 minutes
    local alert_key="$ALERT_SENT_FILE.$(echo "$msg" | md5sum | cut -c1-8)"
    if [ -f "$alert_key" ] && [ "$(find "$alert_key" -mmin -30 2>/dev/null)" ]; then
        return 0
    fi
    touch "$alert_key"

    # Email
    if command -v sendmail &>/dev/null; then
        echo -e "Subject: [HMS ALERT] $msg\nFrom: hms@$DOMAIN\nTo: $ALERT_EMAIL\n\n$msg\n\nServer: $(hostname)\nTime: $(date)" \
            | sendmail "$ALERT_EMAIL" 2>/dev/null || true
    fi

    # Slack
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\":rotating_light: *HMS ALERT*: $msg\"}" \
            "$SLACK_WEBHOOK" > /dev/null 2>&1 || true
    fi
}

FAILURES=0

# ─── Health endpoint ──────────────────────────────────────────────────────────
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$HEALTH_URL" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    alert "Health check failed (HTTP $HTTP_CODE). URL: $HEALTH_URL"
    ((FAILURES++))
else
    # Check for degraded state
    HEALTH_STATUS=$(curl -s "$HEALTH_URL" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
    if [ "$HEALTH_STATUS" != "healthy" ]; then
        alert "Health check degraded: status=$HEALTH_STATUS"
        ((FAILURES++))
    fi
fi

# ─── Gunicorn ────────────────────────────────────────────────────────────────
if ! systemctl is-active --quiet hms-gunicorn; then
    alert "Gunicorn service is DOWN"
    ((FAILURES++))
fi

# ─── Celery ──────────────────────────────────────────────────────────────────
if ! systemctl is-active --quiet hms-celery; then
    alert "Celery worker is DOWN"
    ((FAILURES++))
fi

# ─── Disk space ───────────────────────────────────────────────────────────────
DISK_PCT=$(df / | awk 'NR==2 {gsub("%",""); print $5}')
if [ "$DISK_PCT" -gt 85 ]; then
    alert "Disk usage at ${DISK_PCT}% — approaching capacity"
    ((FAILURES++))
fi

# ─── PostgreSQL ───────────────────────────────────────────────────────────────
if ! sudo -u postgres psql -c "SELECT 1" hms_db > /dev/null 2>&1; then
    alert "PostgreSQL is not accepting connections to hms_db"
    ((FAILURES++))
fi

# ─── SSL certificate expiry ───────────────────────────────────────────────────
if command -v openssl &>/dev/null; then
    CERT_FILE="/etc/letsencrypt/live/$DOMAIN/cert.pem"
    if [ -f "$CERT_FILE" ]; then
        EXPIRY=$(openssl x509 -enddate -noout -in "$CERT_FILE" | cut -d= -f2)
        EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$EXPIRY" +%s 2>/dev/null || echo 0)
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
        if [ "$DAYS_LEFT" -lt 14 ]; then
            alert "SSL certificate for $DOMAIN expires in ${DAYS_LEFT} days — run: certbot renew"
            ((FAILURES++))
        fi
    fi
fi

if [ "$FAILURES" -eq 0 ]; then
    log "All checks passed."
else
    log "$FAILURES check(s) failed."
fi

exit $FAILURES
