# SchoolBridge — Start all development services
# Run from: C:\Users\AMADILE MAJID\Schoolbridge\
# This opens each service in a new PowerShell window automatically.

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ProjectDir

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Starting SchoolBridge Dev Stack" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Use venv only
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "ERROR: venv not found. Create it first (python -m venv venv)." -ForegroundColor Red
    exit 1
}

$VenvDir = 'venv'
Write-Host "Using virtual environment: venv" -ForegroundColor Green

$PyExe = ".\venv\Scripts\python.exe"
$CeleryExe = ".\venv\Scripts\celery.exe"

Write-Host "Running Django system check..." -ForegroundColor Yellow
& $PyExe manage.py check
if ($LASTEXITCODE -ne 0) {
    Write-Host "Django check failed. Fix issues, then run .\start_dev.ps1 again." -ForegroundColor Red
    exit 1
}
Write-Host "  Django check: OK" -ForegroundColor Green

# Check Redis is reachable — if not, try to start Docker container
Write-Host "Checking Redis..." -ForegroundColor Yellow
try {
    $ping = & redis-cli ping 2>&1
    if ($ping -ne "PONG") { throw "no pong" }
    Write-Host "  Redis: already running." -ForegroundColor Green
} catch {
    Write-Host "  Redis not running. Starting Docker container..." -ForegroundColor Yellow
    try {
        # Try to start existing container first
        docker start schoolbridge-redis 2>&1 | Out-Null
        Write-Host "  Redis: Docker container started." -ForegroundColor Green
    } catch {
        # Create new container
        docker run -d --name schoolbridge-redis -p 6379:6379 `
            redis:7-alpine redis-server --appendonly yes 2>&1 | Out-Null
        Write-Host "  Redis: new Docker container created and started." -ForegroundColor Green
    }
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "Opening service windows..." -ForegroundColor Yellow

# Window 1 — Django server
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$ProjectDir'; Write-Host 'Django Server' -ForegroundColor Cyan; .\$VenvDir\Scripts\python.exe manage.py runserver 8002"
)

Start-Sleep -Milliseconds 500

# Window 2 — Celery worker (all queues, solo pool for Windows)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$ProjectDir'; Write-Host 'Celery Worker' -ForegroundColor Cyan; .\$VenvDir\Scripts\celery.exe -A config worker -Q messaging,payments,automation -c 2 -P solo --loglevel=info"
)

Start-Sleep -Milliseconds 500

# Window 3 — Celery Beat
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$ProjectDir'; Write-Host 'Celery Beat' -ForegroundColor Cyan; .\$VenvDir\Scripts\celery.exe -A config beat --loglevel=info"
)

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  All services started!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  API:   http://localhost:8002/api/v1/" -ForegroundColor Cyan
Write-Host "  Admin: http://localhost:8002/admin/" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3 new PowerShell windows have opened:" -ForegroundColor White
Write-Host "  - Django server" -ForegroundColor Gray
Write-Host "  - Celery worker" -ForegroundColor Gray
Write-Host "  - Celery beat" -ForegroundColor Gray
Write-Host ""
