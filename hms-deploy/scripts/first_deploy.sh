#!/usr/bin/env bash
# =============================================================================
# HMS First-Time Deploy — runs on the server as root after setup_server.sh
# Usage: bash first_deploy.sh https://github.com/yourorg/hms.git
# =============================================================================
set -euo pipefail

REPO="${1:?Provide repo URL as first argument}"
APP_DIR="/var/www/hms"
APP_USER="hms"
VENV="$APP_DIR/venv"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== HMS First Deployment ==="

# Ensure env file exists
[ -f /etc/hms/.env ] || { echo "ERROR: /etc/hms/.env not found. Configure it first."; exit 1; }

# Clone repo
log "Cloning repository..."
sudo -u "$APP_USER" git clone "$REPO" "$APP_DIR"

# Virtual environment
log "Creating Python virtual environment..."
sudo -u "$APP_USER" python3.11 -m venv "$VENV"
sudo -u "$APP_USER" "$VENV/bin/pip" install --quiet --upgrade pip wheel
sudo -u "$APP_USER" "$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# Migrations
log "Running database migrations..."
sudo -u "$APP_USER" bash -c "
  source /etc/hms/.env
  export DJANGO_SETTINGS_MODULE=config.settings.production
  cd $APP_DIR
  $VENV/bin/python manage.py migrate --noinput
"

# Superuser
log "Creating admin superuser..."
sudo -u "$APP_USER" bash -c "
  source /etc/hms/.env
  export DJANGO_SETTINGS_MODULE=config.settings.production
  cd $APP_DIR
  $VENV/bin/python manage.py createsuperuser
"

# Static files
log "Collecting static files..."
sudo -u "$APP_USER" bash -c "
  source /etc/hms/.env
  export DJANGO_SETTINGS_MODULE=config.settings.production
  cd $APP_DIR
  $VENV/bin/python manage.py collectstatic --noinput
"

# Static dir ownership for nginx
mkdir -p /var/www/hms/staticfiles
chown -R "$APP_USER:www-data" /var/www/hms/staticfiles
chmod 755 /var/www/hms/staticfiles

# Install systemd services
log "Installing systemd services..."
for svc in hms-gunicorn hms-celery hms-celerybeat; do
    if [ -f "/home/ubuntu/hms-deploy/systemd/${svc}.service" ]; then
        cp "/home/ubuntu/hms-deploy/systemd/${svc}.service" /etc/systemd/system/
    fi
done
systemctl daemon-reload
systemctl enable hms-gunicorn hms-celery hms-celerybeat
systemctl start  hms-gunicorn hms-celery hms-celerybeat

# Install backup script
log "Installing backup script..."
cp /home/ubuntu/hms-deploy/backups/backup.sh /etc/hms/backup.sh
chmod 750 /etc/hms/backup.sh
chown "$APP_USER:$APP_USER" /etc/hms/backup.sh

# Install monitoring
log "Installing monitoring script..."
cp /home/ubuntu/hms-deploy/monitoring/alert.sh /etc/hms/alert.sh
chmod 750 /etc/hms/alert.sh

# Cron jobs
crontab -u "$APP_USER" -l 2>/dev/null | { cat; echo "0 2 * * * /etc/hms/backup.sh >> /var/log/hms/backup.log 2>&1"; } | crontab -u "$APP_USER" -
crontab -u root        -l 2>/dev/null | { cat; echo "*/5 * * * * source /etc/hms/.env && /etc/hms/alert.sh >> /var/log/hms/monitoring.log 2>&1"; } | crontab -u root -

log ""
log "✅ First deployment complete!"
log ""
log "Next steps:"
log "  1. Install TLS: certbot --nginx -d yourdomain.com -d www.yourdomain.com --email you@email.com --agree-tos --redirect"
log "  2. Test health:  curl https://yourdomain.com/health/"
log "  3. Deploy frontend to Vercel/Netlify with VITE_API_URL=https://yourdomain.com/api/v1"
