# ================================================================
# SchoolBridge — Automated Windows Setup Script
# Run from: C:\Users\AMADILE MAJID\Schoolbridge\
# Usage:    .\setup_windows.ps1
# ================================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  SchoolBridge Backend Setup" -ForegroundColor Cyan
Write-Host "  Windows | PostgreSQL | Local" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------
# STEP 1: Detect Python
# ---------------------------------------------------------------
Write-Host "[ 1/10 ] Detecting Python..." -ForegroundColor Yellow

$PythonExe = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 11) {
                $PythonExe = $cmd
                Write-Host "         Found: $ver (using '$cmd')" -ForegroundColor Green
                break
            } else {
                Write-Host "         Found $ver — needs 3.11+. Checking next..." -ForegroundColor Yellow
            }
        }
    } catch {}
}

if (-not $PythonExe) {
    Write-Host ""
    Write-Host "  ERROR: Python 3.11 or higher not found." -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host "  Make sure to check 'Add Python to PATH' during install." -ForegroundColor Yellow
    exit 1
}

# ---------------------------------------------------------------
# STEP 2: Create virtual environment
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 2/10 ] Creating virtual environment..." -ForegroundColor Yellow

if (Test-Path "venv") {
    Write-Host "         venv already exists — skipping." -ForegroundColor Gray
} else {
    & $PythonExe -m venv venv
    Write-Host "         Virtual environment created at .\venv\" -ForegroundColor Green
}

$PipExe = ".\venv\Scripts\pip.exe"
$PyExe  = ".\venv\Scripts\python.exe"

# ---------------------------------------------------------------
# STEP 3: Upgrade pip
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 3/10 ] Upgrading pip inside venv..." -ForegroundColor Yellow
& $PyExe -m pip install --upgrade pip --quiet
Write-Host "         pip upgraded." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 4: Install requirements
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 4/10 ] Installing Python packages (2-4 minutes)..." -ForegroundColor Yellow
Write-Host "         Installing from requirements.txt..." -ForegroundColor Gray

# Install everything except weasyprint first (needs GTK on Windows)
& $PipExe install -r requirements.txt --quiet 2>&1 | ForEach-Object {
    if ($_ -match "error|Error|ERROR") {
        Write-Host "         WARNING: $_" -ForegroundColor Yellow
    }
}

# Try weasyprint separately — will fail on Windows without GTK
try {
    & $PipExe install weasyprint --quiet 2>&1 | Out-Null
    Write-Host "         WeasyPrint: installed." -ForegroundColor Green
} catch {
    Write-Host "         WeasyPrint: skipped (needs GTK on Windows)" -ForegroundColor Yellow
    Write-Host "         PDF report cards will use ReportLab only (already installed)." -ForegroundColor Gray
}

Write-Host "         All packages installed." -ForegroundColor Green

# ---------------------------------------------------------------
# STEP 5: Generate .env
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 5/10 ] Creating .env configuration file..." -ForegroundColor Yellow

if (Test-Path ".env") {
    Write-Host "         .env already exists — skipping to preserve your settings." -ForegroundColor Gray
} else {
    # Auto-generate Django secret key
    $SecretKey = & $PyExe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
    
    # Auto-generate Fernet key for PII field encryption
    $FernetKey = & $PyExe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    Write-Host ""
    Write-Host "         Enter your PostgreSQL password for 'schoolbridge_app' user." -ForegroundColor Cyan
    Write-Host "         (If the user does not exist yet, we will create it next)" -ForegroundColor Gray
    $DbPass = Read-Host "         PostgreSQL password" -AsSecureString
    $DbPassPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DbPass)
    )

    $envContent = @"
# ================================================================
# SchoolBridge Environment Configuration
# Generated by setup_windows.ps1 on $(Get-Date -Format 'yyyy-MM-dd HH:mm')
# NEVER commit this file to git.
# ================================================================

# Django Core
DJANGO_SECRET_KEY=$SecretKey
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
FRONTEND_URL=http://localhost:3000

# Database — PostgreSQL (local)
DB_NAME=schoolbridge
DB_USER=schoolbridge_app
DB_PASSWORD=$DbPassPlain
DB_HOST=localhost
DB_PORT=5432

# Redis (Docker or WSL — see setup guide)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# PII Encryption — AES-256 Fernet (auto-generated, keep secret)
FERNET_KEYS=$FernetKey

# Email — console backend for development
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=SchoolBridge <noreply@schoolbridge.ug>

# WhatsApp Cloud API — Meta (fill in when you have credentials)
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=schoolbridge_verify_$(Get-Random -Minimum 10000 -Maximum 99999)

# Africa's Talking SMS — Uganda
AT_USERNAME=sandbox
AT_API_KEY=
AT_SENDER_ID=SchoolBridge

# Sentry error monitoring (leave empty for development)
SENTRY_DSN=

# CORS — frontend origins
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# File storage (local disk in development)
USE_S3=False

# Celery Flower dashboard credentials
FLOWER_USER=admin
FLOWER_PASSWORD=flower_dev_pass
"@
    $envContent | Out-File -FilePath ".env" -Encoding UTF8 -NoNewline
    Write-Host "         .env created with auto-generated keys." -ForegroundColor Green
    Write-Host "         SECRET_KEY and FERNET_KEY auto-generated." -ForegroundColor Green
    Write-Host "         DB_PASSWORD set to what you entered." -ForegroundColor Green
}

# ---------------------------------------------------------------
# STEP 6: .gitignore
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 6/10 ] Protecting .env in .gitignore..." -ForegroundColor Yellow

$gitignoreContent = @"
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
venv/
env/
.venv/

# Django
*.log
local_settings.py
db.sqlite3
media/
staticfiles/

# Environment — NEVER commit
.env
*.env
.env.*
!.env.example

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Testing
.coverage
htmlcov/
.pytest_cache/

# Celery
celerybeat-schedule
celerybeat.pid

# Build
dist/
build/
*.egg-info/
logs/*.log
"@

if (Test-Path ".gitignore") {
    $existing = Get-Content ".gitignore" -Raw
    if ($existing -notmatch "\.env") {
        Add-Content ".gitignore" "`n.env"
        Write-Host "         Added .env protection to existing .gitignore." -ForegroundColor Green
    } else {
        Write-Host "         .gitignore already protects .env." -ForegroundColor Green
    }
} else {
    $gitignoreContent | Out-File -FilePath ".gitignore" -Encoding UTF8
    Write-Host "         .gitignore created." -ForegroundColor Green
}

# ---------------------------------------------------------------
# STEP 7: Create required directories
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 7/10 ] Creating required directories..." -ForegroundColor Yellow
@("logs", "media", "staticfiles", "templates") | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item -ItemType Directory -Path $_ | Out-Null
        Write-Host "         Created: $_\" -ForegroundColor Green
    } else {
        Write-Host "         Exists:  $_\" -ForegroundColor Gray
    }
}

# Create automation management command directory
$mgmtPath = "automation\management\commands"
if (-not (Test-Path $mgmtPath)) {
    New-Item -ItemType Directory -Path $mgmtPath -Force | Out-Null
    "" | Out-File "automation\management\__init__.py" -Encoding UTF8
    "" | Out-File "automation\management\commands\__init__.py" -Encoding UTF8
    Write-Host "         Created: automation management commands dir" -ForegroundColor Green
}

# ---------------------------------------------------------------
# STEP 8: PostgreSQL database setup
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 8/10 ] Setting up PostgreSQL database..." -ForegroundColor Yellow

# Read DB password from .env
$envDbPass = ""
if (Test-Path ".env") {
    $envLines = Get-Content ".env"
    foreach ($line in $envLines) {
        if ($line -match "^DB_PASSWORD=(.+)$") {
            $envDbPass = $Matches[1]
        }
    }
}

# Find psql
$psqlPath = $null
foreach ($candidate in @(
    "psql",
    "C:\Program Files\PostgreSQL\17\bin\psql.exe",
    "C:\Program Files\PostgreSQL\16\bin\psql.exe",
    "C:\Program Files\PostgreSQL\15\bin\psql.exe",
    "C:\Program Files\PostgreSQL\14\bin\psql.exe"
)) {
    try {
        $testResult = & $candidate --version 2>&1
        if ($testResult -match "PostgreSQL") {
            $psqlPath = $candidate
            break
        }
    } catch {}
}

if ($psqlPath) {
    Write-Host "         Found psql at: $psqlPath" -ForegroundColor Green
    Write-Host "         Creating database and user..." -ForegroundColor Gray
    Write-Host "         (You may be prompted for the PostgreSQL superuser password)" -ForegroundColor Gray
    
    $sqlCommands = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'schoolbridge_app') THEN
    CREATE USER schoolbridge_app WITH PASSWORD '$envDbPass';
  ELSE
    ALTER USER schoolbridge_app WITH PASSWORD '$envDbPass';
  END IF;
END
`$`$;

SELECT 'CREATE DATABASE schoolbridge OWNER schoolbridge_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'schoolbridge')\gexec

GRANT ALL PRIVILEGES ON DATABASE schoolbridge TO schoolbridge_app;

\c schoolbridge
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
"@
    
    try {
        $sqlCommands | & $psqlPath -U postgres --quiet 2>&1
        Write-Host "         Database 'schoolbridge' ready." -ForegroundColor Green
        Write-Host "         User 'schoolbridge_app' configured." -ForegroundColor Green
        Write-Host "         Extensions pg_trgm + uuid-ossp enabled." -ForegroundColor Green
    } catch {
        Write-Host "         Auto-setup failed. Run these SQL commands manually in pgAdmin:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "         CREATE USER schoolbridge_app WITH PASSWORD '$envDbPass';" -ForegroundColor White
        Write-Host "         CREATE DATABASE schoolbridge OWNER schoolbridge_app;" -ForegroundColor White
        Write-Host "         GRANT ALL PRIVILEGES ON DATABASE schoolbridge TO schoolbridge_app;" -ForegroundColor White
        Write-Host "         \c schoolbridge" -ForegroundColor White
        Write-Host "         CREATE EXTENSION IF NOT EXISTS pg_trgm;" -ForegroundColor White
        Write-Host "         CREATE EXTENSION IF NOT EXISTS ""uuid-ossp"";" -ForegroundColor White
    }
} else {
    Write-Host "         psql not found in PATH." -ForegroundColor Yellow
    Write-Host "         Open pgAdmin and run these SQL commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "         CREATE USER schoolbridge_app WITH PASSWORD '$envDbPass';" -ForegroundColor White
    Write-Host "         CREATE DATABASE schoolbridge OWNER schoolbridge_app;" -ForegroundColor White
    Write-Host "         GRANT ALL PRIVILEGES ON DATABASE schoolbridge TO schoolbridge_app;" -ForegroundColor White
    Write-Host "         \c schoolbridge" -ForegroundColor White
    Write-Host "         CREATE EXTENSION IF NOT EXISTS pg_trgm;" -ForegroundColor White
    Write-Host "         CREATE EXTENSION IF NOT EXISTS ""uuid-ossp"";" -ForegroundColor White
    Write-Host ""
    Write-Host "         After running those commands, press ENTER to continue." -ForegroundColor Cyan
    Read-Host "         Press ENTER when database is ready"
}

# ---------------------------------------------------------------
# STEP 9: Run Django migrations
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 9/10 ] Running Django migrations..." -ForegroundColor Yellow

try {
    & $PyExe manage.py migrate 2>&1 | ForEach-Object { Write-Host "         $_" -ForegroundColor Gray }
    Write-Host "         Migrations complete." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "         MIGRATION FAILED. Check:" -ForegroundColor Red
    Write-Host "         1. Is PostgreSQL service running?" -ForegroundColor Yellow
    Write-Host "         2. Is DB_PASSWORD in .env correct?" -ForegroundColor Yellow
    Write-Host "         3. Did you create the database in Step 8?" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "         Fix the issue then run: .\venv\Scripts\python.exe manage.py migrate" -ForegroundColor Cyan
}

# ---------------------------------------------------------------
# STEP 10: Register Celery beat schedule
# ---------------------------------------------------------------
Write-Host ""
Write-Host "[ 10/10 ] Registering Celery periodic task schedule..." -ForegroundColor Yellow

try {
    & $PyExe manage.py setup_periodic_tasks 2>&1 | ForEach-Object {
        Write-Host "          $_" -ForegroundColor Gray
    }
    Write-Host "          Beat schedule registered." -ForegroundColor Green
} catch {
    Write-Host "          Will auto-register on first Celery beat start." -ForegroundColor Gray
}

# ---------------------------------------------------------------
# DONE
# ---------------------------------------------------------------
Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Run these commands to start SchoolBridge:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Create your admin account:" -ForegroundColor Yellow
Write-Host "     .\venv\Scripts\python.exe manage.py createsuperuser" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Start Django server (Window 1):" -ForegroundColor Yellow
Write-Host "     .\venv\Scripts\python.exe manage.py runserver" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. Start Redis via Docker (Window 2):" -ForegroundColor Yellow
Write-Host "     docker run -d --name sb-redis -p 6379:6379 redis:7-alpine redis-server --appendonly yes" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Start Celery worker (Window 3):" -ForegroundColor Yellow
Write-Host "     .\venv\Scripts\celery.exe -A config worker -Q messaging,payments,automation -c 2 -P solo --loglevel=info" -ForegroundColor Cyan
Write-Host ""
Write-Host "  5. Start Celery Beat (Window 4):" -ForegroundColor Yellow
Write-Host "     .\venv\Scripts\celery.exe -A config beat --loglevel=info" -ForegroundColor Cyan
Write-Host ""
Write-Host "  API  : http://localhost:8000/api/v1/" -ForegroundColor Green
Write-Host "  Admin: http://localhost:8000/admin/" -ForegroundColor Green
Write-Host ""
Write-Host "  Read SETUP_GUIDE.md for full documentation." -ForegroundColor Gray
Write-Host ""
