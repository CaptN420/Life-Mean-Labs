@echo off
REM ============================================================
REM  Life_mean Studio — Launcher
REM  Starts the orchestrator server and opens the GUI widget.
REM
REM  Usage:
REM    start_studio.bat
REM ============================================================

setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
cd /d "%ROOT%"
if errorlevel 1 (
    echo [ERROR] Cannot enter "%ROOT%"
    pause
    exit /b 1
)

echo [INFO] Starting Life_mean Studio...

REM --- Start the orchestrator server (port 3000) in its own console ---
REM  NOTE: use /D for the working directory. Nesting "cd /d \"path\"" inside
REM  cmd /c does not work: cmd has no backslash-escaped quotes.
if exist "%ROOT%hermes-orchestrator\node_modules" (
    echo [INFO] Launching Hermes Orchestrator on port 3000...
    start "Hermes Orchestrator" /D "%ROOT%hermes-orchestrator" cmd /c "npm start"
) else (
    echo [WARN] hermes-orchestrator\node_modules missing - orchestrator skipped
    echo [WARN] Run: cd hermes-orchestrator ^&^& npm install
)

REM Wait a moment for server to initialize
ping -n 3 127.0.0.1 >nul

REM --- Open the Studio GUI ---
if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [ERROR] Python venv not found: "%ROOT%.venv\Scripts\python.exe"
    echo [ERROR] Create it with: python -m venv .venv ^&^& .venv\Scripts\pip install -e .
    pause
    exit /b 1
)

echo [INFO] Opening Life_mean Studio widget...
"%ROOT%.venv\Scripts\python.exe" -m life_mean_studio
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] Studio exited with code %RC%
    pause
) else (
    echo [INFO] Studio closed.
)
endlocal
