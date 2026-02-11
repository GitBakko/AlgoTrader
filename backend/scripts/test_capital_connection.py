"""
Test script per verificare la connessione a Capital.com.
Testa REST API e WebSocket con i 3 asset: Gold (XAUUSD), Bitcoin (BTCUSD), S&P 500 (US500).
"""

import asyncio
import sys
from pathlib import Path

# Add backend src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta

from loguru import logger

from src.broker.client import CapitalComClient
from src.broker.models import Resolution
from src.broker.websocket_client import CapitalComWebSocketClient, OHLCData, QuoteData
from src.utils.config import get_settings


async def test_rest_api(client: CapitalComClient) -> dict[str, str]:
    """
    Test REST API connection and find epic codes for our 3 assets.

    Returns:
        Dictionary mapping asset names to epic codes
    """
    logger.info("=" * 60)
    logger.info("🔍 FASE 1: Test REST API - Search Markets")
    logger.info("=" * 60)

    epic_map = {}

    # Connect (authenticate)
    await client.connect()

    # Search for each asset
    assets = [
        ("Gold", "gold"),
        ("Bitcoin", "bitcoin"),
        ("S&P 500", "US500"),
    ]

    for asset_name, search_term in assets:
        logger.info(f"\n🔎 Searching for {asset_name} (term: '{search_term}')...")
        markets = await client.search_markets(search_term)

        if not markets:
            logger.error(f"❌ No markets found for {asset_name}")
            continue

        logger.success(f"✅ Found {len(markets)} markets for {asset_name}:")
        for i, market in enumerate(markets[:5], 1):  # Show first 5
            logger.info(
                f"   {i}. {market.epic} - {market.instrument_name} "
                f"(Bid: {market.bid}, Ask: {market.offer})"
            )

        # Use first result as our epic
        epic = markets[0].epic
        epic_map[asset_name] = epic
        logger.success(f"✅ Selected epic for {asset_name}: {epic}")

    return epic_map


async def test_historical_data(client: CapitalComClient, epic_map: dict[str, str]) -> None:
    """Test historical data download for each asset."""
    logger.info("\n" + "=" * 60)
    logger.info("📊 FASE 2: Test Historical Data (OHLC)")
    logger.info("=" * 60)

    # Download last 10 days of daily data for each asset
    to_date = datetime.now()
    from_date = to_date - timedelta(days=10)

    for asset_name, epic in epic_map.items():
        logger.info(f"\n📈 Downloading historical data for {asset_name} ({epic})...")

        try:
            candles = await client.get_historical_prices(
                epic=epic,
                resolution=Resolution.DAY,
                from_date=from_date,
                to_date=to_date,
                max_candles=10,
            )

            if candles:
                logger.success(f"✅ Downloaded {len(candles)} daily candles for {asset_name}")
                logger.info(f"   First candle: {candles[0].timestamp} - OHLC: "
                           f"{candles[0].open:.2f} / {candles[0].high:.2f} / "
                           f"{candles[0].low:.2f} / {candles[0].close:.2f}")
                logger.info(f"   Last candle:  {candles[-1].timestamp} - OHLC: "
                           f"{candles[-1].open:.2f} / {candles[-1].high:.2f} / "
                           f"{candles[-1].low:.2f} / {candles[-1].close:.2f}")
            else:
                logger.warning(f"⚠️  No historical data returned for {asset_name}")

        except Exception as e:
            logger.error(f"❌ Error downloading historical data for {asset_name}: {e}")


async def test_account_info(client: CapitalComClient) -> None:
    """Test account information retrieval."""
    logger.info("\n" + "=" * 60)
    logger.info("💰 FASE 3: Test Account Information")
    logger.info("=" * 60)

    try:
        accounts = await client.get_accounts()

        if accounts:
            for account in accounts:
                logger.success(f"✅ Account: {account.account_name} ({account.account_type})")
                logger.info(f"   Account ID: {account.account_id}")
                logger.info(f"   Currency: {account.currency}")
                logger.info(f"   Balance: {account.balance:.2f}")
                logger.info(f"   Available: {account.available:.2f}")
                logger.info(f"   P&L: {account.profit_loss:.2f}")
        else:
            logger.warning("⚠️  No accounts found")

    except Exception as e:
        logger.error(f"❌ Error retrieving account info: {e}")


async def test_websocket(client: CapitalComClient, epic_map: dict[str, str]) -> None:
    """Test WebSocket streaming for real-time quotes."""
    logger.info("\n" + "=" * 60)
    logger.info("📡 FASE 4: Test WebSocket Real-Time Streaming")
    logger.info("=" * 60)

    settings = get_settings()
    ws_url = (
        settings.capital_demo_ws_url if settings.use_demo else settings.capital_live_ws_url
    )

    ws_client = CapitalComWebSocketClient(
        ws_url=ws_url,
        session_manager=client.session_manager,
        max_reconnect_attempts=3,
        reconnect_delay_seconds=2,
    )

    # Quote counter
    quote_count = {}
    ohlc_count = {}

    async def on_quote(quote: QuoteData):
        """Handle incoming quote."""
        if quote.epic not in quote_count:
            quote_count[quote.epic] = 0
        quote_count[quote.epic] += 1

        logger.info(
            f"📊 QUOTE [{quote.epic}] #{quote_count[quote.epic]} - "
            f"Bid: {quote.bid:.2f} | Ask: {quote.offer:.2f} | "
            f"Spread: {(quote.offer - quote.bid):.2f} | "
            f"Time: {quote.timestamp.strftime('%H:%M:%S')}"
        )

    async def on_ohlc(ohlc: OHLCData):
        """Handle incoming OHLC candle."""
        if ohlc.epic not in ohlc_count:
            ohlc_count[ohlc.epic] = 0
        ohlc_count[ohlc.epic] += 1

        logger.info(
            f"📈 OHLC [{ohlc.epic}] {ohlc.resolution} #{ohlc_count[ohlc.epic]} - "
            f"O: {ohlc.open:.2f} H: {ohlc.high:.2f} L: {ohlc.low:.2f} C: {ohlc.close:.2f} | "
            f"Time: {ohlc.datetime.strftime('%H:%M:%S')}"
        )

    # Register handlers
    ws_client.on_quote(on_quote)
    ws_client.on_ohlc(on_ohlc)

    try:
        # Connect
        logger.info("\n🔌 Connecting to WebSocket...")
        await ws_client.connect()

        # Subscribe to quotes for all 3 assets
        epics = list(epic_map.values())
        logger.info(f"\n📡 Subscribing to real-time quotes for: {epics}")
        await ws_client.subscribe_quotes(epics)

        # Subscribe to 5-minute OHLC candles
        logger.info(f"\n📊 Subscribing to 5-minute OHLC candles for: {epics}")
        await ws_client.subscribe_ohlc(epics, ["MINUTE_5"])

        # Listen for 30 seconds
        logger.info("\n⏱️  Listening for 30 seconds...\n")
        await asyncio.sleep(30)

        logger.info("\n" + "=" * 60)
        logger.info("📊 WebSocket Statistics:")
        logger.info(f"   Quotes received: {sum(quote_count.values())}")
        for epic, count in quote_count.items():
            logger.info(f"      - {epic}: {count} quotes")
        logger.info(f"   OHLC candles received: {sum(ohlc_count.values())}")
        for epic, count in ohlc_count.items():
            logger.info(f"      - {epic}: {count} candles")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
    finally:
        await ws_client.disconnect()


async def main():
    """Main test function."""
    logger.info("\n" + "🚀" * 30)
    logger.info("🎯 AlgoTrader AI - Capital.com Connection Test")
    logger.info("🚀" * 30 + "\n")

    settings = get_settings()

    # Verify credentials are configured
    if settings.use_demo:
        logger.info("📝 Using DEMO account")
        if not settings.capital_demo_api_key or not settings.capital_demo_email:
            logger.error("❌ Demo credentials not configured in .env file!")
            logger.error("   Please set CAPITAL_DEMO_API_KEY, CAPITAL_DEMO_EMAIL, CAPITAL_DEMO_PASSWORD")
            return
    else:
        logger.warning("⚠️  Using LIVE account - BE CAREFUL!")
        if not settings.capital_live_api_key or not settings.capital_live_email:
            logger.error("❌ Live credentials not configured in .env file!")
            return

    # Create client
    client = CapitalComClient()

    try:
        # Test 1: REST API - Search markets and find epic codes
        epic_map = await test_rest_api(client)

        if not epic_map:
            logger.error("❌ No epic codes found - cannot continue tests")
            return

        # Test 2: Historical data
        await test_historical_data(client, epic_map)

        # Test 3: Account information
        await test_account_info(client)

        # Test 4: WebSocket streaming
        await test_websocket(client, epic_map)

        logger.info("\n" + "✅" * 30)
        logger.success("🎉 All tests completed successfully!")
        logger.info("✅" * 30 + "\n")

    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {e}", exc_info=True)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
