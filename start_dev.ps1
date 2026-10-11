# SchoolBridge — Start all development services
# Run from: C:\Users\AMADILE MAJID\Schoolbridge\
# Uses existing Docker containers (edubridge_postgres on 5432, edubridge_redis on 6379)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ProjectDir

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Starting SchoolBridge Dev Stack" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Check venv exists ---
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "ERROR: .venv not found. Run: python -m venv .venv" -ForegroundColor Red
    exit 1
}

$VenvDir  = '.venv'
$PyExe    = ".\.venv\Scripts\python.exe"
$CeleryExe = ".\.venv\Scripts\celery.exe"

Write-Host "  Virtual environment: .venv" -ForegroundColor Green

# --- 2. Verify Docker containers are running ---
Write-Host ""
Write-Host "Checking Docker infrastructure..." -ForegroundColor Yellow

# Verify Docker daemon is running
& docker ps 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker daemon is not running or accessible." -ForegroundColor Red
    Write-Host "Please start Docker Desktop and retry." -ForegroundColor Yellow
    exit 1
}

$requiredContainers = @(
    @{ Name = "edubridge_postgres"; Label = "PostgreSQL (port 5432)" },
    @{ Name = "edubridge_redis";    Label = "Redis      (port 6379)" }
)

$allReady = $true
foreach ($c in $requiredContainers) {
    $status = docker inspect --format "{{.State.Status}}" $c.Name 2>&1
    if ($status -eq "running") {
        Write-Host "  [OK] $($c.Label)" -ForegroundColor Green
    } else {
        Write-Host "  [..] $($c.Label) is not running (status: $status). Starting..." -ForegroundColor Yellow
        docker start $c.Name > $null 2>&1
        
        # Poll up to 3 times to check if it started successfully
        $started = $false
        for ($i = 1; $i -le 3; $i++) {
            Start-Sleep -Seconds 2
            $status = docker inspect --format "{{.State.Status}}" $c.Name 2>&1
            if ($status -eq "running") {
                $started = $true
                break
            }
        }
        
        if ($started) {
            Write-Host "  [OK] $($c.Label) started successfully." -ForegroundColor Green
        } else {
            Write-Host "  [!!] $($c.Label) failed to start." -ForegroundColor Red
            $allReady = $false
        }
    }
}

if (-not $allReady) {
    Write-Host ""
    Write-Host "ERROR: One or more required containers are not running." -ForegroundColor Red
    Write-Host "Please start Docker Desktop and retry." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "  All infrastructure containers are healthy." -ForegroundColor Green

# --- 3. Django system check ---
Write-Host ""
Write-Host "Running Django system check..." -ForegroundColor Yellow
& $PyExe manage.py check 2>&1 | Where-Object { $_ -notmatch "RequestsDependencyWarning" }
if ($LASTEXITCODE -ne 0) {
    Write-Host "Django check failed. Fix issues then run .\start_dev.ps1 again." -ForegroundColor Red
    exit 1
}
Write-Host "  Django check: OK" -ForegroundColor Green

# --- 4. Open service windows ---
Write-Host ""
Write-Host "Opening service windows..." -ForegroundColor Yellow

# Window 1 — Django server
Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-NoExit",
    "-Command",
    "Set-Location '$ProjectDir'; & '.\.venv\Scripts\Activate.ps1'; `$host.UI.RawUI.WindowTitle = 'SchoolBridge | Django :8002'; Write-Host '=== SchoolBridge Django Server ===' -ForegroundColor Cyan; python manage.py runserver 8002"
)

Start-Sleep -Milliseconds 800

# Window 2 — Celery worker (all queues, solo pool for Windows)
Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-NoExit",
    "-Command",
    "Set-Location '$ProjectDir'; & '.\.venv\Scripts\Activate.ps1'; `$host.UI.RawUI.WindowTitle = 'SchoolBridge | Celery Worker'; Write-Host '=== SchoolBridge Celery Worker ===' -ForegroundColor Cyan; celery -A config worker -Q messaging,payments,automation,bulk,realtime,celery -c 2 -P solo --loglevel=info"
)

Start-Sleep -Milliseconds 800

# Window 3 — Celery Beat
Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-NoExit",
    "-Command",
    "Set-Location '$ProjectDir'; & '.\.venv\Scripts\Activate.ps1'; `$host.UI.RawUI.WindowTitle = 'SchoolBridge | Celery Beat'; Write-Host '=== SchoolBridge Celery Beat ===' -ForegroundColor Cyan; celery -A config beat --loglevel=info"
)

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  All services launched!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  API:    http://localhost:8002/api/v1/" -ForegroundColor Cyan
Write-Host "  Admin:  http://localhost:8002/admin/" -ForegroundColor Cyan
Write-Host "  Docs:   http://localhost:8002/api/docs/" -ForegroundColor Cyan
Write-Host "  Schema: http://localhost:8002/api/schema/" -ForegroundColor Cyan
Write-Host "  Health: http://localhost:8002/health/" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3 windows opened:" -ForegroundColor White
Write-Host "    Window 1 - Django server (port 8002)" -ForegroundColor Gray
Write-Host "    Window 2 - Celery worker (messaging, payments, automation)" -ForegroundColor Gray
Write-Host "    Window 3 - Celery beat (scheduled tasks)" -ForegroundColor Gray
Write-Host ""
