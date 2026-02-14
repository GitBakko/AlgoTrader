@echo off
echo ========================================
echo   MANTIS AI - Frontend Startup
echo ========================================
echo.
echo Starting Angular dev server on http://localhost:4321
echo Press Ctrl+C to stop
echo.

cd frontend
call npx ng serve --port 4321
