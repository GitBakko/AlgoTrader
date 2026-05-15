"""Quick test for Marketaux API fix."""
import asyncio
from src.external.marketaux_client import MarketauxClient

async def test_marketaux():
    """Test Marketaux news sentiment."""
    print("[TEST] Initializing Marketaux client...")
    client = MarketauxClient()

    print("[TEST] Fetching NVDA news (limit=5, days=7)...")
    try:
        articles = await client.get_news_sentiment("NVDA", limit=5, days=7)

        if articles:
            print(f"[SUCCESS] Fetched {len(articles)} articles")
            for i, article in enumerate(articles, 1):
                print(f"\n[{i}] {article.title}")
                print(f"    Sentiment: {article.sentiment:.3f}")
                print(f"    Published: {article.published_at}")
                print(f"    Entities: {', '.join(article.entities)}")
        else:
            print("[WARNING] No articles returned")

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

    finally:
        await client.close()
        print("\n[TEST] Client closed")

if __name__ == "__main__":
    asyncio.run(test_marketaux())
