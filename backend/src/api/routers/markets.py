"""
Markets API router.
Provides market search, OHLC price data, and market info.
"""

from fastapi import APIRouter, Path, Query

from src.api.schemas import MarketInfo, OHLCResponse, error_response, success_response

router = APIRouter()

# Static market list for MVP (no broker connection required)
SUPPORTED_MARKETS = [
    MarketInfo(epic="XAUUSD", name="Gold (XAU/USD)", change_pct=0.0),
    MarketInfo(epic="BTCUSD", name="Bitcoin (BTC/USD)", change_pct=0.0),
    MarketInfo(epic="US500", name="S&P 500 (US500)", change_pct=0.0),
]

_MARKET_MAP = {m.epic: m for m in SUPPORTED_MARKETS}


@router.get("/search")
async def search_markets(q: str = Query(default="", min_length=0)):
    """Search available markets by name or epic."""
    query = q.lower()
    if not query:
        results = SUPPORTED_MARKETS
    else:
        results = [
            m
            for m in SUPPORTED_MARKETS
            if query in m.epic.lower() or query in m.name.lower()
        ]

    return success_response([m.model_dump() for m in results])


@router.get("/{epic}/info")
async def get_market_info(epic: str = Path(...)):
    """Get market information for a specific epic."""
    market = _MARKET_MAP.get(epic.upper())
    if market is None:
        return error_response(f"Market {epic} not found", 404)

    return success_response(market.model_dump())


@router.get("/{epic}/prices")
async def get_market_prices(
    epic: str = Path(...),
    resolution: str = Query(default="HOUR"),
    max_candles: int = Query(default=200, ge=1, le=1000),
):
    """
    Get historical OHLC prices for an asset.
    MVP: returns empty list. Full implementation reads from Parquet/DuckDB storage.
    """
    # TODO: Read from src/data/storage.py or DuckDB once historical data is available
    return success_response([])
