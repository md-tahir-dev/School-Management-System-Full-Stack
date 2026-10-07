@echo off
setlocal
cd /d "%~dp0"

call :stop_process ".sms-backend.pid" "uvicorn app.main:app" "backend"
call :stop_process ".sms-frontend.pid" "npm run dev" "frontend"

echo Finished stopping the tracked project processes.
pause
endlocal
exit /b 0

:stop_process
if not exist "%~1" (
    echo No tracked %~3 process found.
    exit /b 0
)

set /p TARGET_PID=<"%~1"
powershell -NoProfile -Command "$id = 0; if (-not [int]::TryParse('%TARGET_PID%', [ref]$id)) { Write-Error 'Invalid process ID file.'; exit 1 }; $p = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $id); if ($p -and $p.CommandLine -like '*%~2*') { taskkill.exe /PID $id /T /F; exit $LASTEXITCODE } else { Write-Output 'No matching %~3 process is running.' }"
if errorlevel 1 (
    echo WARNING: Could not stop the tracked %~3 process.
)
del /Q "%~1" >nul 2>&1
exit /b 0
