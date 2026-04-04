# HMS — Hospital Management System
Complete full-stack project. See DEPLOYMENT_GUIDE.md inside hms-deploy/ for setup steps.

## Folders
- hms/            → Django backend (Python)
- hms-frontend/   → React frontend (TypeScript)
- hms-deploy/     → Server setup & deployment scripts
- hms-enterprise/ → Docker, Redis caching, SMS, performance

## Quick local start

### Backend
cd hms
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

### Frontend
cd hms-frontend
npm install
cp .env.example .env            # set VITE_API_URL=http://localhost:8000/api/v1
npm run dev
# HMS
