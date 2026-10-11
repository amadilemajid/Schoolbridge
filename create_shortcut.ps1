# SchoolBridge — Create Desktop Shortcut for Dev Environment
# Run from: C:\Users\AMADILE MAJID\Schoolbridge\
# Usage:    .\create_shortcut.ps1

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ProjectDir

Write-Host ""
Write-Host "Creating SchoolBridge Dev Environment Desktop Shortcut..." -ForegroundColor Cyan

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = [Environment]::GetFolderPath('Desktop')
    $ShortcutPath = Join-Path $DesktopPath "SchoolBridge Dev Environment.lnk"
    
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = Join-Path $ProjectDir "start_dev.bat"
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.Description = "Start Django, Celery Worker, and Celery Beat for SchoolBridge"
    $Shortcut.IconLocation = "cmd.exe,0"
    $Shortcut.Save()
    
    Write-Host "[OK] Desktop shortcut created successfully at:" -ForegroundColor Green
    Write-Host "     $ShortcutPath" -ForegroundColor White
} catch {
    Write-Host "ERROR: Failed to create shortcut." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}
Write-Host ""
