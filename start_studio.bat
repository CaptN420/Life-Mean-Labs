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

echo [INFO] Starting Life_mean Studio...

REM --- Start the orchestrator server in background ---
echo [INFO] Launching Hermes Orchestrator on port 3000...
start "" cmd /c "cd /d \"%ROOT%hermes-orchestrator\" && npm start"

REM Wait a moment for server to initialize
ping -n 3 localhost >nul

REM --- Open the Studio GUI ---
echo [INFO] Opening Life_mean Studio widget...
"%ROOT%.venv/Scripts/python.exe" -m life_mean_studio

echo [INFO] Studio closed.
endlocal
