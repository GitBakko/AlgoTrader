@echo off
echo ========================================
echo   MANTIS AI - Dual-Source News Backend
echo ========================================
echo.
echo [INFO] Starting backend with Finnhub + Marketaux integration...
echo.
echo Backend will be available at: http://127.0.0.1:8000
echo API Documentation: http://127.0.0.1:8000/docs
echo.
echo Press Ctrl+C to stop the backend
echo.

cd backend
.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
