# SchoolBridge — Run test suite
# Usage: .\run_tests.ps1
#        .\run_tests.ps1 -Module payments
#        .\run_tests.ps1 -Module auth

param([string]$Module = "")

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Definition)

if ($Module) {
    Write-Host "Running tests for module: $Module" -ForegroundColor Cyan
    & .\venv\Scripts\python.exe manage.py test tests.test_$Module -v 2
} else {
    Write-Host "Running all tests..." -ForegroundColor Cyan
    & .\venv\Scripts\python.exe manage.py test tests/ -v 2
}
