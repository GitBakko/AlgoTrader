"""
News and sentiment API endpoints.
Provides access to news articles, insider sentiment, and aggregated sentiment scores.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from loguru import logger

from src.api.dependencies import get_finnhub_client, get_marketaux_client
from src.api.schemas import error_response, success_response
from src.external.finnhub_client import FinnhubClient
from src.external.marketaux_client import MarketauxClient

router = APIRouter()


@router.get("/{epic}")
async def get_news(
    epic: str,
    limit: int = Query(default=20, ge=1, le=100, description="Max articles to return"),
    days: int = Query(default=7, ge=1, le=30, description="Lookback period in days"),
    marketaux: MarketauxClient | None = Depends(get_marketaux_client),
    finnhub: FinnhubClient | None = Depends(get_finnhub_client),
):
    """
    Get news articles with sentiment scores for an asset.

    Fetches from BOTH Marketaux and Finnhub, merges results, and returns sorted by date.
    Each article includes a 'source' field indicating the provider.

    Returns:
        List of news articles with title, description, URL, sentiment score, published date, and source.
    """
    logger.info(f"Fetching news for {epic}, limit={limit}, days={days}")

    all_articles = []

    # Fetch from Marketaux (with sentiment)
    if marketaux is not None:
        try:
            marketaux_articles = await marketaux.get_news_sentiment(epic, limit, days)
            logger.info(f"Got {len(marketaux_articles)} articles from Marketaux")
            all_articles.extend(marketaux_articles)
        except Exception as e:
            logger.warning(f"Marketaux fetch failed: {e}")

    # Fetch from Finnhub (company news)
    if finnhub is not None:
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            end_date = datetime.now(timezone.utc)
            finnhub_articles = await finnhub.get_company_news(epic, start_date, end_date)
            logger.info(f"Got {len(finnhub_articles)} articles from Finnhub")
            all_articles.extend(finnhub_articles)
        except Exception as e:
            logger.warning(f"Finnhub fetch failed: {e}")

    # If both sources failed or returned empty
    if not all_articles:
        logger.warning(f"No news articles available for {epic} from any source")
        return success_response([])

    # Sort by published_at (most recent first)
    all_articles.sort(key=lambda x: x.published_at, reverse=True)

    # Limit to requested count
    all_articles = all_articles[:limit]

    logger.info(f"Returning {len(all_articles)} total articles for {epic}")

    return success_response(
        [
            {
                "title": a.title,
                "description": a.description,
                "url": a.url,
                "published_at": a.published_at.isoformat(),
                "sentiment": round(a.sentiment, 3),
                "entities": a.entities,
                "source": a.source,  # Source identifier (finnhub/marketaux)
                "thumbnail": a.thumbnail,  # Thumbnail image URL (optional)
            }
            for a in all_articles
        ]
    )


@router.get("/insider/{epic}")
async def get_insider_sentiment(
    epic: str,
    start_date: str | None = Query(default=None, description="Start date (ISO format)"),
    end_date: str | None = Query(default=None, description="End date (ISO format)"),
    finnhub: FinnhubClient | None = Depends(get_finnhub_client),
):
    """
    Get insider sentiment (MSPR - Monthly Share Purchase Ratio) for a stock.

    MSPR indicates whether insiders are buying (positive) or selling (negative).

    Returns:
        Insider sentiment data with MSPR score, change, and period.
    """
    if finnhub is None:
        return error_response("Finnhub service not available", 503)

    try:
        # Parse dates or use defaults (last 180 days)
        if start_date is None:
            start = datetime.now(timezone.utc) - timedelta(days=180)
        else:
            start = datetime.fromisoformat(start_date)

        if end_date is None:
            end = datetime.now(timezone.utc)
        else:
            end = datetime.fromisoformat(end_date)

        insider = await finnhub.get_insider_sentiment(epic, start, end)

        if insider is None:
            return error_response("No insider data available", 404)

        return success_response(
            {
                "epic": insider.epic,
                "mspr": round(insider.mspr, 2),
                "change": insider.change,
                "period": insider.period,
            }
        )
    except Exception as e:
        return error_response(str(e), 500)


@router.get("/sentiment/{epic}")
async def get_sentiment_summary(
    epic: str,
    days: int = Query(default=7, ge=1, le=30, description="Lookback period in days"),
    marketaux: MarketauxClient | None = Depends(get_marketaux_client),
):
    """
    Get aggregated sentiment score for an asset.

    Calculates the average sentiment across recent news articles.

    Returns:
        Sentiment score (-1.0 to 1.0), article count, and period.
    """
    if marketaux is None:
        return error_response("Sentiment service not available", 503)

    try:
        sentiment = await marketaux.get_aggregated_sentiment(epic, days)
        articles = await marketaux.get_news_sentiment(epic, limit=100, days=days)

        return success_response(
            {
                "epic": epic,
                "sentiment": round(sentiment, 3),
                "article_count": len(articles),
                "period_days": days,
            }
        )
    except Exception as e:
        return error_response(str(e), 500)
