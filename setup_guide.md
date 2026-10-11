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

## STEP 9 — Run Django and Celery Services (Automated — Recommended)

You can launch all services (Django server, Celery worker, Celery beat) automatically. 
- Ensure **Docker Desktop** is running.
- If you ran `create_shortcut.ps1`, you can simply double-click the **SchoolBridge Dev Environment** shortcut on your Desktop.
- Alternatively, double-click `start_dev.bat` in the root folder, or execute:
  ```powershell
  .\start_dev.ps1
  ```
The script will perform safety and environment checks and open 3 PowerShell windows for your development stack.

---

## STEP 10 — Run Services Manually (Fallback / Alternative)

If you prefer to start the services manually in separate PowerShell windows:

### Window 1 — Django Server (port 8002):
```powershell
.\venv\Scripts\Activate.ps1
python manage.py runserver 8002
```
API: http://localhost:8002/api/v1/ | Admin: http://localhost:8002/admin/

### Window 2 — Celery Worker (all queues, solo pool for Windows):
```powershell
.\venv\Scripts\Activate.ps1
celery -A config worker -Q messaging,payments,automation -c 2 --loglevel=info -P solo
```

### Window 3 — Celery Beat (scheduled tasks):
```powershell
.\venv\Scripts\Activate.ps1
celery -A config beat --loglevel=info
```

*Note: `-P solo` is required on Windows as Celery does not support the fork-based pool architecture natively on Windows.*

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
