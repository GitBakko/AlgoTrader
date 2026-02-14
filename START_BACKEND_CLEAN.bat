@echo off
title MANTIS AI - Backend Server
color 0A
echo.
echo ================================================
echo    MANTIS AI - Backend Server (Dual-Source)
echo ================================================
echo.
echo [INFO] Starting backend on http://127.0.0.1:8000
echo [INFO] API Docs: http://127.0.0.1:8000/docs
echo.
echo Press Ctrl+C to stop
echo.

cd /d "%~dp0backend"
.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

pause
