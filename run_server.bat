@echo off
REM ============================================================
REM  Life_mean — Dashboard server launcher
REM  URL:  http://127.0.0.1:8080/dashboard
REM
REM  Usage:
REM    run_server.bat            start the dashboard on :8080
REM    run_server.bat 8081       start on a custom port
REM ============================================================
setlocal enabledelayedexpansion
chcp 65001 >nul

REM ---- resolve project root and CD into it (works from any launch point) ----
set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "%ROOT%experiments\dashboard.py" (
    echo [ERROR] Could not find experiments\dashboard.py in "%ROOT%"
    echo         Run this script from inside the Life_mean project.
    pause
    exit /b 1
)

set "PORT=8080"
for %%A in (%*) do (
    if not "%%A"=="" set "PORT=%%A"
)

REM ---- free any zombie listener on PORT ----
echo [1/3] Releasing port %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
    echo       killing PID %%P on port %PORT%
    taskkill /F /PID %%P >nul 2>&1
)
timeout /t 1 /nobreak >nul 2>&1

REM ---- locate a working Python (probe the real import; skip the
REM       WindowsApps "python" stub that only opens the Microsoft Store) ----
set "PYCMD="
python -c "import experiments.dashboard" >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD py -3 -c "import experiments.dashboard" >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD (
    echo [ERROR] No working Python found. The dashboard needs Python 3 with
    echo         the project dependencies installed.
    echo.
    echo   If you saw "Python was not found; run without arguments to install
    echo   from the Microsoft Store", the WindowsApps "python" stub is shadowing
    echo   your real Python. Disable it in:  Settings ^> Apps ^> Advanced app
    echo   settings ^> App execution aliases, or add a real Python to PATH.
    pause
    exit /b 1
)

REM ---- run the dashboard ----
echo [2/3] Launched Life_mean dashboard on port %PORT%
echo       URL: http://127.0.0.1:%PORT%/dashboard
echo [3/3] Press Ctrl+C to stop.
echo.
%PYCMD% -m experiments.dashboard --host 127.0.0.1 --port %PORT%
set "RC=%ERRORLEVEL%"
echo.

if not "%RC%"=="0" (
    echo [ERROR] The dashboard exited with code %RC%.
    echo         The window is held open so you can read the message above.
) else (
    echo Server stopped.
)
pause
exit /b %RC%
