@echo off
echo ========================================
echo   MANTIS AI - Dual-Source News Test
echo ========================================
echo.
echo [INFO] Testing Finnhub + Marketaux integration...
echo.

echo [1] Health Check
curl -s http://127.0.0.1:8000/health | python -m json.tool | findstr /C:"status" /C:"app_name"
echo.
echo.

echo [2] Dual-Source News (NVDA, last 3 days, limit 5)
echo    Expected: Finnhub articles (Marketaux at daily limit)
curl -s "http://127.0.0.1:8000/api/news/NVDA?limit=5&days=3" | python -m json.tool | head -80
echo.
echo.

echo [3] Check Sources Distribution
curl -s "http://127.0.0.1:8000/api/news/NVDA?limit=20&days=7" > temp_news.json
python -c "import json; data=json.load(open('temp_news.json')); articles=data.get('data',[]); print(f'\nTotal articles: {len(articles)}'); print(f'Finnhub: {sum(1 for a in articles if a.get(\"source\")==\"finnhub\")}'); print(f'Marketaux: {sum(1 for a in articles if a.get(\"source\")==\"marketaux\")}')" 2>nul
del temp_news.json 2>nul
echo.
echo.

echo ========================================
echo   Test Complete!
echo ========================================
echo.
echo [INFO] Frontend: http://localhost:4321/news
echo        Navigate to see news with source badges!
echo.
pause
