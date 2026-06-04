@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo Starting Celery Worker...
celery -A config worker -l info --pool=solo
pause
