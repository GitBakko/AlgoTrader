@echo off
echo ================================================
echo    Test Dual-Source News System
echo ================================================
echo.

echo [1] Testing NVDA News (5 articles, 2 days)
curl -s "http://127.0.0.1:8000/api/news/NVDA?limit=5&days=2" | python -m json.tool
echo.
echo.

echo [2] Testing TSLA News (3 articles, 3 days)
curl -s "http://127.0.0.1:8000/api/news/TSLA?limit=3&days=3" | python -m json.tool
echo.
echo.

echo ================================================
echo    Test Complete!
echo ================================================
echo.
echo Expected: Articles with "source": "finnhub"
echo Frontend: http://localhost:4321/news
echo.
pause
