# Start Celery Worker and Beat in separate windows
Write-Host "Starting Celery Worker and Beat..." -ForegroundColor Green

# Start Celery Worker in new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\AMADILE MAJID\Schoolbridge'; .\venv\Scripts\Activate.ps1; celery -A config worker -l info --pool=solo"

# Wait 2 seconds
Start-Sleep -Seconds 2

# Start Celery Beat in new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\AMADILE MAJID\Schoolbridge'; .\venv\Scripts\Activate.ps1; celery -A config beat -l info"

Write-Host "Celery Worker and Beat started in separate windows" -ForegroundColor Green
Write-Host "Press any key to exit..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
