@echo off
cd /d "%~dp0"
echo Starting SchoolBridge Development Environment...
powershell -ExecutionPolicy Bypass -File "start_dev.ps1"
pause
