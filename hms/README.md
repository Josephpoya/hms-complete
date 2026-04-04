# Hospital Management System — Django Backend

## Project structure

```
hms/
├── config/
│   ├── settings/
│   │   ├── base.py          # shared settings
│   │   ├── development.py   # local dev overrides
│   │   └── production.py    # production hardening
│   ├── urls.py              # root URL configuration
│   ├── celery.py            # Celery app instance
│   ├── pagination.py        # standard DRF pagination
│   └── exceptions.py        # global exception handler
├── accounts/                # custom User model, JWT auth, RBAC, AuditLog
├── patients/                # patient demographics
├── doctors/                 # doctor profiles
├── appointments/            # scheduling
├── billing/                 # invoices and payments
├── pharmacy/                # drugs and prescriptions
├── records/                 # electronic health records
├── manage.py
├── requirements.txt
└── .env.example
```

---

## Quickstart (local development)

### 1 — Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### 2 — Clone and create virtual environment

```bash
git clone <repo-url> hms
cd hms
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
```

### 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### 4 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your local values:

```env
SECRET_KEY=local-dev-secret-key-change-in-production
DEBUG=True
DATABASE_URL=postgres://hms_user:password@localhost:5432/hms_db
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### 5 — Create the PostgreSQL database

```bash
psql -U postgres
```

```sql
CREATE USER hms_user WITH PASSWORD 'password';
CREATE DATABASE hms_db OWNER hms_user;
GRANT ALL PRIVILEGES ON DATABASE hms_db TO hms_user;
\q
```

### 6 — Run migrations

```bash
export DJANGO_SETTINGS_MODULE=config.settings.development
python manage.py migrate
```

### 7 — Create a superuser (Admin)

```bash
python manage.py createsuperuser
# You will be prompted for email, role, and password
```

### 8 — Run the development server

```bash
python manage.py runserver
```

API is available at: `http://localhost:8000/api/v1/`  
Swagger UI: `http://localhost:8000/api/schema/swagger/`  
Django Admin: `http://localhost:8000/admin/`

---

## Running Celery (async tasks)

In a separate terminal:

```bash
# Worker
celery -A config worker --loglevel=info

# Beat scheduler (periodic tasks)
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Authentication flow

```
POST /api/v1/auth/login/
  Body: { "email": "user@hospital.com", "password": "..." }
  Response: { "access": "<jwt>", "refresh": "<jwt>" }

# Use access token on subsequent requests:
  Authorization: Bearer <access-token>

POST /api/v1/auth/refresh/
  Body: { "refresh": "<refresh-token>" }
  Response: { "access": "<new-access-token>" }

POST /api/v1/auth/logout/
  Body: { "refresh": "<refresh-token>" }
  # Blacklists the refresh token
```

---

## Running tests

```bash
pytest
pytest --cov=. --cov-report=html   # with coverage report
```

---

## Production deployment checklist

- [ ] Set `DEBUG=False` in `.env`
- [ ] Set strong `SECRET_KEY` (50+ random characters)
- [ ] Configure `ALLOWED_HOSTS` with real domain
- [ ] Set up PostgreSQL with SSL
- [ ] Configure S3 bucket and AWS credentials
- [ ] Set `SENTRY_DSN` for error tracking
- [ ] Run `python manage.py collectstatic`
- [ ] Set up Nginx reverse proxy with TLS
- [ ] Configure Gunicorn: `gunicorn config.wsgi:application --workers 4 --bind 0.0.0.0:8000`
- [ ] Set up Celery as a systemd service
- [ ] Enable PostgreSQL WAL archiving for backups
- [ ] Restrict DB user permissions (INSERT-only on audit_auditlog)
