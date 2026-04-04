# HMS Production Deployment Guide

A complete, step-by-step guide to deploying the Hospital Management System
on a single Ubuntu 22.04 LTS server. Estimated time: 60–90 minutes.

---

## Architecture Overview

```
Internet
    │
    ▼
[Cloudflare / DNS]
    │  HTTPS
    ▼
[Nginx — port 443]          ← TLS termination, rate limiting, static files
    │  Unix socket
    ▼
[Gunicorn — 4 workers]      ← Django WSGI server
    │
    ├──► [PostgreSQL 14]     ← Primary datastore
    ├──► [Redis 7]           ← Cache + Celery broker
    └──► [AWS S3]            ← Document storage

[Celery Worker]             ← Async tasks (running separately)
[Celery Beat]               ← Periodic task scheduler
```

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS          | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| CPU         | 2 vCPUs | 4 vCPUs |
| RAM         | 2 GB    | 4 GB |
| Disk        | 20 GB SSD | 50 GB SSD |
| Domain      | Required (for TLS) | Required |
| AWS account | Required (S3) | Required |

---

## Phase 1: Server Setup

### 1.1 Connect to your server

```bash
ssh root@your-server-ip
```

### 1.2 Run the automated setup script

This installs all dependencies, creates the system user, configures
PostgreSQL and Redis, and sets up the firewall.

```bash
# Upload the setup script
scp scripts/setup_server.sh root@your-server-ip:/tmp/

# Run it (replace with your domain and email)
bash /tmp/setup_server.sh yourdomain.com your@email.com
```

What it does:
- Updates system packages
- Installs Python 3.11, PostgreSQL 14, Redis 7, Nginx, Certbot
- Creates the `hms` system user
- Creates PostgreSQL database `hms_db` and user `hms_user`
- Configures Redis with a password and memory limits
- Sets up UFW firewall (SSH + HTTP/HTTPS only)
- Configures fail2ban for brute-force protection
- Sets up log rotation

### 1.3 Note the Redis password

The script prints the generated Redis password. Save it — you'll need it in
the next step:

```
Redis password set to: abc123xyz...
Add to /etc/hms/.env as: REDIS_URL=redis://:abc123xyz@localhost:6379/0
```

---

## Phase 2: Configure Environment

### 2.1 Create the environment file

```bash
# Create the secure config directory (already done by setup script)
mkdir -p /etc/hms

# Copy the template
cp .env.production /etc/hms/.env

# Lock down permissions — CRITICAL
chmod 600 /etc/hms/.env
chown hms:hms /etc/hms/.env
```

### 2.2 Edit the environment file

```bash
nano /etc/hms/.env
```

Fill in every value:

```env
# Generate a strong secret key:
# python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY=your-generated-50-char-key

DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Use the password PostgreSQL was set up with
DATABASE_URL=postgres://hms_user:STRONG_DB_PASSWORD@localhost:5432/hms_db

# Use the Redis password from the setup script output
REDIS_URL=redis://:REDIS_PASSWORD@localhost:6379/0
CELERY_BROKER_URL=redis://:REDIS_PASSWORD@localhost:6379/1
CELERY_RESULT_BACKEND=redis://:REDIS_PASSWORD@localhost:6379/2

# AWS S3
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_STORAGE_BUCKET_NAME=hms-documents-production
AWS_S3_REGION_NAME=af-south-1

# Sentry (get DSN from sentry.io)
SENTRY_DSN=https://xxx@yyy.ingest.sentry.io/zzz

# CORS — your frontend URL
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```

### 2.3 Change the PostgreSQL user password

```bash
sudo -u postgres psql
```
```sql
ALTER USER hms_user WITH PASSWORD 'STRONG_DB_PASSWORD';
\q
```

---

## Phase 3: Deploy the Application

### 3.1 Deploy as the hms user

```bash
# Switch to the hms user
su - hms

# Clone the repository
git clone https://github.com/yourorg/hms.git /var/www/hms
cd /var/www/hms

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip wheel
pip install -r requirements.txt

# Run database migrations
DJANGO_SETTINGS_MODULE=config.settings.production \
python manage.py migrate

# Create the superuser (admin account)
DJANGO_SETTINGS_MODULE=config.settings.production \
python manage.py createsuperuser

# Collect static files
DJANGO_SETTINGS_MODULE=config.settings.production \
python manage.py collectstatic --noinput

# Create static file directory if needed
mkdir -p /var/www/hms/staticfiles
```

### 3.2 Run Django deployment checks

```bash
DJANGO_SETTINGS_MODULE=config.settings.production \
python manage.py check --deploy
```

All warnings should be resolved before going live. Common fixes:
- `SECURE_SSL_REDIRECT = True` — already set in production.py
- `SESSION_COOKIE_SECURE = True` — already set
- `CSRF_COOKIE_SECURE = True` — already set

---

## Phase 4: Configure Nginx

### 4.1 Install the Nginx configuration

```bash
# Edit to replace yourdomain.com
nano nginx/hms.conf

# Copy to Nginx
sudo cp nginx/hms.conf /etc/nginx/sites-available/hms

# Enable the site
sudo ln -sf /etc/nginx/sites-available/hms /etc/nginx/sites-enabled/hms

# Remove the default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Reload (not restart — preserves existing connections)
sudo systemctl reload nginx
```

### 4.2 Install TLS certificate (Let's Encrypt)

```bash
sudo certbot --nginx \
    -d yourdomain.com \
    -d www.yourdomain.com \
    --email your@email.com \
    --agree-tos \
    --redirect \
    --non-interactive
```

Certbot auto-renews via a systemd timer. Verify:

```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

---

## Phase 5: Configure systemd Services

### 5.1 Install service files

```bash
sudo cp systemd/hms-gunicorn.service   /etc/systemd/system/
sudo cp systemd/hms-celery.service     /etc/systemd/system/
sudo cp systemd/hms-celerybeat.service /etc/systemd/system/

sudo systemctl daemon-reload

# Enable services (start on boot)
sudo systemctl enable hms-gunicorn hms-celery hms-celerybeat

# Start services
sudo systemctl start hms-gunicorn hms-celery hms-celerybeat
```

### 5.2 Verify all services are running

```bash
sudo systemctl status hms-gunicorn
sudo systemctl status hms-celery
sudo systemctl status hms-celerybeat

# Check logs
sudo journalctl -u hms-gunicorn -n 50 --no-pager
sudo journalctl -u hms-celery   -n 30 --no-pager
```

### 5.3 Smoke test

```bash
curl -s https://yourdomain.com/health/ | python3 -m json.tool
```

Expected response:
```json
{
  "status": "healthy",
  "total_ms": 12.4,
  "checks": {
    "database": { "status": "ok", "latency_ms": 3.2 },
    "cache":    { "status": "ok", "latency_ms": 1.1 },
    "disk":     { "status": "ok", "pct_used": 28.4, "free_gb": 35.2 }
  }
}
```

---

## Phase 6: Frontend Deployment

The React frontend is a static SPA that can be deployed to Vercel, Netlify,
or served directly from Nginx. Vercel is recommended for the easiest setup.

### Option A: Vercel (Recommended)

1. **Push frontend to GitHub**

```bash
cd hms-frontend
git init
git remote add origin https://github.com/yourorg/hms-frontend.git
git push -u origin main
```

2. **Connect to Vercel**

- Go to [vercel.com](https://vercel.com) → New Project
- Import your `hms-frontend` repository
- Framework preset: **Vite**
- Build command: `npm run build`
- Output directory: `dist`

3. **Set environment variable in Vercel dashboard**

```
VITE_API_URL = https://yourdomain.com/api/v1
```

4. **Configure custom domain** in Vercel project settings

5. **Update CORS on the backend**

```bash
nano /etc/hms/.env
# Add your Vercel domain:
# CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://hms-frontend.vercel.app
sudo systemctl reload hms-gunicorn
```

### Option B: Netlify

1. **In the hms-frontend directory**, create `netlify.toml`:

```toml
[build]
  command     = "npm run build"
  publish     = "dist"

[[redirects]]
  from   = "/*"
  to     = "/index.html"
  status = 200
```

2. Drag-and-drop the `dist/` folder to [app.netlify.com](https://app.netlify.com)
   or connect your GitHub repository.

3. Set environment variable: `VITE_API_URL = https://yourdomain.com/api/v1`

### Option C: Serve from Nginx (same server)

```bash
# Build the frontend
cd hms-frontend
npm install
VITE_API_URL=https://yourdomain.com/api/v1 npm run build

# Copy to web root
sudo mkdir -p /var/www/hms-frontend
sudo cp -r dist/* /var/www/hms-frontend/
```

Add to the Nginx server block:

```nginx
# Frontend SPA
location / {
    root /var/www/hms-frontend;
    try_files $uri $uri/ /index.html;
    expires 1h;
    add_header Cache-Control "public, must-revalidate";
}
```

---

## Phase 7: Backup Strategy

### 7.1 Install the backup script

```bash
sudo cp backups/backup.sh /etc/hms/backup.sh
sudo chmod 750 /etc/hms/backup.sh
sudo chown hms:hms /etc/hms/backup.sh

# Create WAL archive directory
sudo mkdir -p /var/backups/hms/wal
sudo chown postgres:postgres /var/backups/hms/wal
```

### 7.2 Schedule daily backups (cron)

```bash
sudo crontab -u hms -e
```

Add:
```cron
# Daily database backup at 02:00
0 2 * * * /etc/hms/backup.sh >> /var/log/hms/backup.log 2>&1

# Weekly full backup to S3 on Sunday at 03:00
0 3 * * 0 /etc/hms/backup.sh >> /var/log/hms/backup.log 2>&1
```

### 7.3 Backup verification (monthly)

Run a test restore on a separate server or locally:

```bash
# Download a backup from S3
aws s3 cp s3://your-bucket/database-backups/hms_db_latest.sql.gz /tmp/

# Verify it can be read
sudo -u postgres pg_restore --list /tmp/hms_db_latest.sql.gz | head -20
```

### 7.4 Retention policy

| Storage         | Retention  | Where           |
|-----------------|-----------|-----------------|
| Daily dumps     | 7 days    | Local `/var/backups/hms/` |
| Weekly dumps    | 30 days   | AWS S3 Standard-IA |
| Monthly dumps   | 7 years   | AWS S3 Glacier  |
| WAL archives    | 3 days    | Local → S3      |

```bash
# Add S3 lifecycle rule (run once)
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-bucket \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "archive-old-backups",
      "Status": "Enabled",
      "Filter": {"Prefix": "database-backups/"},
      "Transitions": [
        {"Days": 30, "StorageClass": "STANDARD_IA"},
        {"Days": 90, "StorageClass": "GLACIER"}
      ],
      "Expiration": {"Days": 2555}
    }]
  }'
```

---

## Phase 8: Monitoring Setup

### 8.1 Install alert script

```bash
sudo cp monitoring/alert.sh /etc/hms/alert.sh
sudo chmod 750 /etc/hms/alert.sh

# Add alert email and optional Slack webhook to .env
echo "HMS_ALERT_EMAIL=admin@yourdomain.com"  >> /etc/hms/.env
echo "HMS_SLACK_WEBHOOK=https://hooks.slack.com/..." >> /etc/hms/.env
```

### 8.2 Schedule monitoring checks

```bash
sudo crontab -u root -e
```

Add:
```cron
# Health check every 5 minutes
*/5 * * * * source /etc/hms/.env && /etc/hms/alert.sh >> /var/log/hms/monitoring.log 2>&1

# SSL certificate check daily
0 6 * * * source /etc/hms/.env && /etc/hms/alert.sh >> /var/log/hms/monitoring.log 2>&1
```

### 8.3 Prometheus + Grafana (optional, recommended for larger deployments)

```bash
# Install node_exporter for system metrics
wget https://github.com/prometheus/node_exporter/releases/latest/download/node_exporter-*.linux-amd64.tar.gz
# Follow Prometheus installation docs for your setup
```

Django exposes Prometheus-compatible metrics via `django-prometheus` if added
to `INSTALLED_APPS`. The `config/settings/base.py` has structured logging
already configured for log aggregation tools (Datadog, CloudWatch, ELK).

---

## Phase 9: Ongoing Operations

### Zero-downtime deployment (after initial setup)

```bash
# On the server, run as hms user:
bash /var/www/hms/deploy.sh

# Or from CI/CD:
ssh hms@your-server "bash /var/www/hms/deploy.sh --branch main"
```

### Reload Gunicorn without dropping connections

```bash
sudo systemctl reload hms-gunicorn
# Sends SIGUSR2 — workers finish their requests, then new workers start
```

### Common service commands

```bash
# Status overview
sudo systemctl status hms-gunicorn hms-celery hms-celerybeat

# Live application logs
sudo journalctl -u hms-gunicorn -f

# Live celery logs
sudo journalctl -u hms-celery -f

# Nginx access log
sudo tail -f /var/log/nginx/hms_access.log

# Application error log
sudo tail -f /var/log/hms/gunicorn.log

# Security log
sudo tail -f /var/log/hms/security.log
```

### Emergency rollback

```bash
cd /var/www/hms
git log --oneline -10             # Find the last good commit
git reset --hard <commit-hash>
sudo systemctl reload hms-gunicorn
```

---

## Security Checklist

Run before going live:

- [ ] `/etc/hms/.env` has `chmod 600` and is owned by `hms:hms`
- [ ] `DEBUG=False` in `.env`
- [ ] Strong `SECRET_KEY` (50+ chars, generated, not shared)
- [ ] PostgreSQL `hms_user` has a strong password
- [ ] Redis requires a password
- [ ] UFW firewall active — only ports 22, 80, 443 open
- [ ] Fail2ban running and configured
- [ ] TLS certificate installed and auto-renewing
- [ ] Django Admin URL restricted to VPN/office IPs in nginx config
- [ ] `python manage.py check --deploy` passes with no warnings
- [ ] Sentry DSN configured for error tracking
- [ ] Backup cron job running: `crontab -u hms -l`
- [ ] Monitoring alert script running: test with `/etc/hms/alert.sh`
- [ ] S3 bucket has `Block Public Access` enabled
- [ ] AWS IAM user has minimal permissions (S3 only)

---

## Troubleshooting

### 502 Bad Gateway

Gunicorn isn't running or the socket doesn't exist:

```bash
sudo systemctl status hms-gunicorn
sudo journalctl -u hms-gunicorn -n 50
ls -la /run/hms/           # Socket should exist
```

### Database connection errors

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test the connection directly
sudo -u hms PGPASSWORD=your_password psql -U hms_user -h localhost hms_db -c "SELECT 1"
```

### Static files returning 404

```bash
# Re-run collectstatic
sudo -u hms bash -c "
  source /etc/hms/.env
  cd /var/www/hms
  venv/bin/python manage.py collectstatic --noinput
"

# Check nginx alias path matches STATIC_ROOT
grep -n "static" /etc/nginx/sites-available/hms
grep "STATIC_ROOT" /var/www/hms/config/settings/base.py
```

### Celery tasks not running

```bash
# Check celery is connected to Redis
sudo -u hms bash -c "
  source /etc/hms/.env
  cd /var/www/hms
  venv/bin/celery --app config inspect active
"
```

### Check HTTPS / TLS

```bash
curl -I https://yourdomain.com/health/
openssl s_client -connect yourdomain.com:443 -brief
```
