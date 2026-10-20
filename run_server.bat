@echo off
REM ============================================================
REM  Life_mean — Docker dashboard launcher
REM  URL:  http://localhost:8080/dashboard
REM
REM  Usage:
REM    run_server.bat            start the Docker dashboard on :8080
REM    run_server.bat 8081       start on a custom host port
REM ============================================================
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

REM --- Single-instance guard: prevent two simultaneous runs ---
set "LOCKFILE=%ROOT%.run_server.lock"
if exist "%LOCKFILE%" (
    echo [ERROR] run_server.bat is already running.
    echo         If this is wrong, delete "%LOCKFILE%" and retry.
    pause
    exit /b 1
)
echo lock> "%LOCKFILE%"

if not exist "%ROOT%docker-compose.yml" (
    echo [ERROR] Could not find docker-compose.yml in "%ROOT%"
    pause
    exit /b 1
)

set "PORT=8080"
if not "%~1"=="" set "PORT=%~1"
set "LIFE_MEAN_PORT=%PORT%"

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker was not found on PATH.
    echo         Install and start Docker Desktop, then retry.
    pause
    exit /b 1
)

echo [1/3] Building and starting the Life_mean Docker dashboard...
docker compose up -d --build
if errorlevel 1 (
    echo [ERROR] Docker Compose could not start the dashboard.
    docker compose logs --tail 50 dashboard
    pause
    exit /b 1
)

echo [1.5/3] Synchronizing host data into the dashboard volume...
"%ROOT%.venv\Scripts\python.exe" "%ROOT%sync_dashboard_data.py"
if errorlevel 1 (
    echo [WARN] Data sync failed - dashboard will start with existing volume data.
)

echo [2/3] Dashboard launched on port %PORT%
echo       URL: http://localhost:%PORT%/dashboard

echo [3/3] Container status:
docker compose ps
start "" "http://localhost:%PORT%/dashboard"
echo.
echo The container is running. Use "docker compose down" to stop it.
del "%LOCKFILE%" >nul 2>&1
pause
exit /b 0
