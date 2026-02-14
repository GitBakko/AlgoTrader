@echo off
echo ========================================
echo   MANTIS AI - API Test Suite
echo ========================================
echo.
echo Testing backend endpoints...
echo.

echo [1] Health Check
curl -s http://127.0.0.1:8000/health
echo.
echo.

echo [2] Insider Sentiment (NVDA)
curl -s "http://127.0.0.1:8000/api/news/insider/NVDA"
echo.
echo.

echo [3] News Articles (NVDA, 5 articles, 7 days)
curl -s "http://127.0.0.1:8000/api/news/NVDA?limit=5&days=7"
echo.
echo.

echo [4] Sentiment Summary (NVDA, 7 days)
curl -s "http://127.0.0.1:8000/api/news/sentiment/NVDA?days=7"
echo.
echo.

echo ========================================
echo   Test complete
echo ========================================
pause
