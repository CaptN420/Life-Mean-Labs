@echo off
REM Hermes Debate Runner
cd /d "%~dp0"

REM Use Hermes agent's Python (has hermes_debate installed)
set PYTHON="C:\Users\celes\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"

REM Run the debate with default topic
%PYTHON% main.py --topic "What is the meaning of life?" %*

REM Keep window open to see output/errors
pause
