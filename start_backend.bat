@echo off
echo ========================================
echo   MANTIS AI - Backend Startup
echo ========================================
echo.
echo Starting FastAPI server on http://127.0.0.1:8000
echo Press Ctrl+C to stop
echo.

cd backend
.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
