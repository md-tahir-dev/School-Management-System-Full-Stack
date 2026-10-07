@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.12 was not found on PATH.
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js and npm were not found on PATH.
    pause
    exit /b 1
)

if not exist "frontend\node_modules\next\package.json" (
    echo ERROR: Frontend dependencies are missing. Run "npm install" in the frontend folder.
    pause
    exit /b 1
)

if not exist "backend\.env" (
    copy /Y "backend\.env.example" "backend\.env" >nul
    echo Created backend\.env from backend\.env.example.
    echo Edit DATABASE_URL and JWT_SECRET in backend\.env, then run this file again.
    pause
    exit /b 1
)

findstr /X /C:"DATABASE_URL=postgresql+asyncpg://sms:CHANGE_ME@localhost:5432/sms" "backend\.env" >nul
if not errorlevel 1 (
    echo ERROR: Set DATABASE_URL in backend\.env to match your local PostgreSQL credentials.
    pause
    exit /b 1
)

findstr /X /C:"JWT_SECRET=CHANGE_ME_generate_a_random_secret" "backend\.env" >nul
if not errorlevel 1 (
    echo ERROR: Set a random JWT_SECRET of at least 32 characters in backend\.env.
    pause
    exit /b 1
)

pushd "backend"
python -m alembic upgrade head
if errorlevel 1 (
    echo ERROR: Database migrations failed. Check PostgreSQL and DATABASE_URL in backend\.env.
    popd
    pause
    exit /b 1
)

python -m scripts.seed
if errorlevel 1 (
    echo ERROR: Database seeding failed. Check the backend output above.
    popd
    pause
    exit /b 1
)
popd

powershell -NoProfile -Command "$p = Start-Process -FilePath 'python' -ArgumentList '-m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000' -WorkingDirectory '%~dp0backend' -PassThru; $p.Id | Set-Content -LiteralPath '%~dp0.sms-backend.pid'"
if errorlevel 1 (
    echo ERROR: Could not start the backend process.
    pause
    exit /b 1
)

powershell -NoProfile -Command "$p = Start-Process -FilePath $env:ComSpec -ArgumentList '/k', 'npm run dev -- --hostname 127.0.0.1' -WorkingDirectory '%~dp0frontend' -PassThru; $p.Id | Set-Content -LiteralPath '%~dp0.sms-frontend.pid'"
if errorlevel 1 (
    echo ERROR: Could not start the frontend process. Run stop_services.bat to stop the backend.
    pause
    exit /b 1
)

echo.
echo Backend and frontend started.
echo Web app: http://localhost:3000
echo API docs: http://localhost:8000/docs
echo PostgreSQL must be running locally before starting.
pause
endlocal
