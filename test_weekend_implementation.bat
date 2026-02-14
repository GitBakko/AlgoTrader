@echo off
echo ========================================
echo   MANTIS AI - Weekend Implementation Test
echo ========================================
echo.
echo [INFO] Testing backend sentiment API endpoints...
echo.

echo [1] Health Check
curl -s http://127.0.0.1:8000/health | python -m json.tool
echo.
echo.

echo [2] Finnhub Insider Sentiment (NVDA)
curl -s "http://127.0.0.1:8000/api/news/insider/NVDA" | python -m json.tool
echo.
echo.

echo [3] Marketaux News with Sentiment (NVDA, 5 articles, 7 days)
curl -s "http://127.0.0.1:8000/api/news/NVDA?limit=5&days=7" | python -m json.tool
echo.
echo.

echo [4] Aggregated Sentiment Score (NVDA, 7 days)
curl -s "http://127.0.0.1:8000/api/news/sentiment/NVDA?days=7" | python -m json.tool
echo.
echo.

echo ========================================
echo   Backend Tests Complete!
echo ========================================
echo.
echo [INFO] Frontend is available at: http://localhost:4321/news
echo [INFO] To test frontend:
echo   1. Start backend:  start_backend.bat
echo   2. Start frontend: start_frontend.bat
echo   3. Navigate to:    http://localhost:4321/news
echo.
pause
