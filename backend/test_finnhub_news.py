"""Test Finnhub company news endpoint."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from src.external.finnhub_client import FinnhubClient
from loguru import logger


async def main():
    client = FinnhubClient()

    logger.info(f"API Key configured: {'Yes' if client.api_key else 'No'}")

    start_date = datetime.now() - timedelta(days=7)
    end_date = datetime.now()

    logger.info(f"Fetching company news for NVDA from {start_date.date()} to {end_date.date()}...")
    articles = await client.get_company_news("NVDA", start_date, end_date)

    logger.info(f"Got {len(articles)} articles")
    for i, article in enumerate(articles[:5], 1):
        logger.info(f"{i}. {article.title[:80]}...")
        logger.info(f"   Source: {article.source} | Published: {article.published_at}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
