# SchoolBridge Backend — Full Setup Guide
## Windows (PowerShell) | Python | PostgreSQL | Redis | Celery

---

## STEP 1 — Verify Python and pip

Run in PowerShell:
```powershell
python --version
pip --version
```
Expected: Python 3.11+ and pip 23+

---

## STEP 2 — Create and activate virtual environment

```powershell
cd C:\Users\AMADILE MAJID\Schoolbridge
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If you get an execution policy error, run this first:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

You should see (venv) at the start of your prompt.

---

## STEP 3 — Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

NOTE: WeasyPrint requires GTK on Windows.
If WeasyPrint fails, install it via:
https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
Then retry pip install.

---

## STEP 4 — PostgreSQL setup

### Option A: PostgreSQL installed locally
1. Open pgAdmin or psql as superuser
2. Run:
```sql
CREATE USER schoolbridge_app WITH PASSWORD 'your_strong_password';
CREATE DATABASE schoolbridge OWNER schoolbridge_app;
GRANT ALL PRIVILEGES ON DATABASE schoolbridge TO schoolbridge_app;
\c schoolbridge
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Option B: Docker (recommended for Windows)
```powershell
docker run -d `
  --name schoolbridge-postgres `
  -e POSTGRES_DB=schoolbridge `
  -e POSTGRES_USER=schoolbridge_app `
  -e POSTGRES_PASSWORD=schoolbridge_dev_pass `
  -p 5432:5432 `
  postgres:15-alpine
```

---

## STEP 5 — Redis setup

### Option A: Docker (recommended for Windows — Redis has no native Windows binary)
```powershell
docker run -d `
  --name schoolbridge-redis `
  -p 6379:6379 `
  redis:7-alpine redis-server --appendonly yes
```

### Option B: WSL2
```bash
sudo apt-get install redis-server
sudo service redis-server start
```

---

## STEP 6 — Configure environment variables

Copy .env.example to .env:
```powershell
Copy-Item .env.example .env
```
Then edit .env with your values (see .env.example comments).

---

## STEP 7 — Run database migrations

```powershell
python manage.py migrate
```

---

## STEP 8 — Create superuser (System Admin)

```powershell
python manage.py createsuperuser
```
Enter: email, first name, last name, password.

---

## STEP 9 — Run the development server

```powershell
python manage.py runserver
```

API available at: http://localhost:8000/api/v1/
Admin panel: http://localhost:8000/admin/

---

## STEP 10 — Run Celery workers (separate PowerShell windows)

### Window 1 — Messaging worker:
```powershell
.\venv\Scripts\Activate.ps1
celery -A config worker -Q messaging -c 2 --loglevel=info -P solo
```

### Window 2 — Payments worker:
```powershell
.\venv\Scripts\Activate.ps1
celery -A config worker -Q payments -c 1 --loglevel=info -P solo
```

### Window 3 — Automation worker:
```powershell
.\venv\Scripts\Activate.ps1
celery -A config worker -Q automation -c 1 --loglevel=info -P solo
```

### Window 4 — Celery Beat (scheduled tasks):
```powershell
.\venv\Scripts\Activate.ps1
celery -A config beat --loglevel=info
```

NOTE: -P solo is required on Windows (no fork support).

---

## STEP 11 — Verify everything is working

```powershell
python manage.py check --deploy
python manage.py test tests/ -v 2
```

---

## FOLDER STRUCTURE (what every folder does)

```
Schoolbridge/
├── config/             # Django project config (settings, urls, celery, asgi)
├── schools/            # Multi-tenant foundation — School, Term, Calendar
├── authentication/     # Users, JWT auth, roles, password reset
├── students/           # Students, guardians, class groups, CSV import
├── payments/           # Fees, MoMo IPN, reconciliation, payment plans
├── messaging/          # WhatsApp, SMS, inbound commands, broadcasts
├── results/            # Marks, UNEB report cards (PLE/UCE/UACE)
├── attendance/         # Daily register, summaries, alerts
├── notifications/      # In-app alerts, WebSocket (Django Channels)
├── audit/              # Immutable audit log
├── automation/         # Celery tasks, beat schedule, calendar service
├── tests/              # All test suites
├── templates/          # HTML email templates
├── scripts/            # DB init, deployment scripts
├── .env.example        # Environment variable template
├── requirements.txt    # All Python dependencies
├── Dockerfile          # Container build
└── docker-compose.yml  # Full stack (web + celery + postgres + redis)
```
