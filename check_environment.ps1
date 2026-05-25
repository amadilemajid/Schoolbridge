# SchoolBridge — Environment Check Script
# Run this in PowerShell from your project directory:
# .\check_environment.ps1

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  SchoolBridge Environment Check" -ForegroundColor Cyan  
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# --- Python ---
Write-Host "[ PYTHON ]" -ForegroundColor Yellow
try {
    $pyVersion = & python --version 2>&1
    Write-Host "  python   : $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  python   : NOT FOUND" -ForegroundColor Red
}

try {
    $py3Version = & python3 --version 2>&1
    Write-Host "  python3  : $py3Version" -ForegroundColor Green
} catch {
    Write-Host "  python3  : not found (OK if python works)" -ForegroundColor Gray
}

try {
    $pyPath = & where.exe python 2>&1
    Write-Host "  location : $pyPath" -ForegroundColor Gray
} catch {}

Write-Host ""

# --- pip ---
Write-Host "[ PIP ]" -ForegroundColor Yellow
try {
    $pipVersion = & pip --version 2>&1
    Write-Host "  pip      : $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "  pip      : NOT FOUND" -ForegroundColor Red
}

Write-Host ""

# --- PostgreSQL ---
Write-Host "[ POSTGRESQL ]" -ForegroundColor Yellow
try {
    $pgVersion = & psql --version 2>&1
    Write-Host "  psql     : $pgVersion" -ForegroundColor Green
} catch {
    Write-Host "  psql     : NOT FOUND in PATH (may still be installed)" -ForegroundColor Yellow
    Write-Host "             Try: C:\Program Files\PostgreSQL\<version>\bin\psql.exe --version" -ForegroundColor Gray
}

# Check if PostgreSQL service is running
try {
    $pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
    if ($pgService) {
        $status = $pgService.Status
        $name   = $pgService.Name
        if ($status -eq "Running") {
            Write-Host "  service  : $name is RUNNING" -ForegroundColor Green
        } else {
            Write-Host "  service  : $name is $status (needs to be started)" -ForegroundColor Red
        }
    } else {
        Write-Host "  service  : No PostgreSQL service found in Windows services" -ForegroundColor Yellow
    }
} catch {}

Write-Host ""

# --- Redis ---
Write-Host "[ REDIS ]" -ForegroundColor Yellow
try {
    $redisVersion = & redis-server --version 2>&1
    Write-Host "  redis    : $redisVersion" -ForegroundColor Green
} catch {
    Write-Host "  redis    : NOT FOUND (will need Docker or WSL)" -ForegroundColor Yellow
}

# Test if Redis is reachable
try {
    $redisPing = & redis-cli ping 2>&1
    if ($redisPing -eq "PONG") {
        Write-Host "  status   : REACHABLE (ping = PONG)" -ForegroundColor Green
    }
} catch {
    Write-Host "  status   : Not reachable on localhost:6379" -ForegroundColor Yellow
}

Write-Host ""

# --- Docker ---
Write-Host "[ DOCKER ]" -ForegroundColor Yellow
try {
    $dockerVersion = & docker --version 2>&1
    Write-Host "  docker   : $dockerVersion" -ForegroundColor Green
    try {
        $dockerRunning = & docker ps 2>&1
        Write-Host "  status   : Docker daemon is RUNNING" -ForegroundColor Green
    } catch {
        Write-Host "  status   : Docker installed but daemon not running" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  docker   : NOT FOUND" -ForegroundColor Gray
}

Write-Host ""

# --- Git ---
Write-Host "[ GIT ]" -ForegroundColor Yellow
try {
    $gitVersion = & git --version 2>&1
    Write-Host "  git      : $gitVersion" -ForegroundColor Green
} catch {
    Write-Host "  git      : NOT FOUND - install from https://git-scm.com" -ForegroundColor Red
}

Write-Host ""

# --- Project directory check ---
Write-Host "[ PROJECT FILES ]" -ForegroundColor Yellow
$requiredFiles = @("manage.py", "config\settings.py", "requirements.txt", ".env.example")
foreach ($f in $requiredFiles) {
    if (Test-Path $f) {
        Write-Host "  [OK]  $f" -ForegroundColor Green
    } else {
        Write-Host "  [!!]  $f  -- MISSING" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Paste this output to Claude for" -ForegroundColor White
Write-Host "  your personalised setup commands." -ForegroundColor White
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
