@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo Starting Celery Beat...
celery -A config beat -l info
pause
