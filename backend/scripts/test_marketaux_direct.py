"""Test MarketauxClient directly."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.external.marketaux_client import MarketauxClient
from loguru import logger


async def main():
    client = MarketauxClient()

    logger.info(f"API Key configured: {'Yes' if client.api_key else 'No'}")
    logger.info(f"API Key (first 10 chars): {client.api_key[:10]}..." if client.api_key else "No key")

    logger.info("Fetching news for NVDA...")
    articles = await client.get_news_sentiment("NVDA", limit=5, days=7)

    logger.info(f"Got {len(articles)} articles")
    for i, article in enumerate(articles[:3], 1):
        logger.info(f"{i}. {article.title} | Sentiment: {article.sentiment:.3f}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
