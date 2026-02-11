"""
Markets API router.
Provides market search, OHLC price data, and market info.
Uses broker client when available, falls back to static data.
"""

from fastapi import APIRouter, Depends, Path, Query
from loguru import logger

from src.api.dependencies import get_broker_client, get_data_access
from src.api.schemas import MarketInfo, OHLCResponse, error_response, success_response

router = APIRouter()

# Static market list (fallback when no broker connection)
SUPPORTED_MARKETS = [
    MarketInfo(epic="XAUUSD", name="Gold (XAU/USD)", change_pct=0.0),
    MarketInfo(epic="BTCUSD", name="Bitcoin (BTC/USD)", change_pct=0.0),
    MarketInfo(epic="US500", name="S&P 500 (US500)", change_pct=0.0),
]

_MARKET_MAP = {m.epic: m for m in SUPPORTED_MARKETS}

# Resolution mapping: API param -> Capital.com Resolution enum value
_RESOLUTION_MAP = {
    "MINUTE": "MINUTE",
    "MINUTE_5": "MINUTE_5",
    "MINUTE_15": "MINUTE_15",
    "HOUR": "HOUR",
    "HOUR_4": "HOUR_4",
    "DAY": "DAY",
    "WEEK": "WEEK",
}

# Resolution -> data pipeline timeframe mapping
_RESOLUTION_TO_TIMEFRAME = {
    "MINUTE": "1min",
    "MINUTE_5": "5min",
    "MINUTE_15": "15min",
    "HOUR": "1h",
    "HOUR_4": "4h",
    "DAY": "1d",
    "WEEK": "1w",
}


@router.get("/search")
async def search_markets(
    q: str = Query(default="", min_length=0),
    broker=Depends(get_broker_client),
):
    """Search available markets by name or epic."""
    # Try broker search first
    if broker and q:
        try:
            from src.broker.models import Market

            broker_markets = await broker.search_markets(q)
            results = [
                MarketInfo(
                    epic=m.epic,
                    name=m.instrument_name,
                    change_pct=getattr(m, "percentage_change", 0.0) or 0.0,
                ).model_dump()
                for m in broker_markets[:20]
            ]
            return success_response(results)
        except Exception as e:
            logger.debug(f"Broker search failed, using static list: {e}")

    # Fallback to static list
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
    data_access=Depends(get_data_access),
    broker=Depends(get_broker_client),
):
    """
    Get historical OHLC prices for an asset.
    Reads from local Parquet storage first, falls back to broker API.
    """
    # Try local data first
    if data_access:
        timeframe = _RESOLUTION_TO_TIMEFRAME.get(resolution.upper(), "1h")
        try:
            df = data_access.get_candles(epic.upper(), timeframe, limit=max_candles)
            if not df.is_empty():
                # Use Polars native serialization (much faster than per-row Pydantic)
                df = df.tail(max_candles)
                candles = [
                    {
                        "timestamp": str(row["timestamp"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row.get("volume", 0) or 0),
                    }
                    for row in df.to_dicts()
                ]
                return success_response(candles)
        except Exception as e:
            logger.debug(f"Local data read failed: {e}")

    # Try broker API
    if broker:
        try:
            from src.broker.models import Resolution

            res = Resolution(resolution.upper()) if resolution.upper() in _RESOLUTION_MAP else Resolution.HOUR
            candles_raw = await broker.get_historical_prices(
                epic=epic.upper(), resolution=res, max_candles=max_candles
            )
            candles = [
                OHLCResponse(
                    timestamp=str(c.snapshot_time),
                    open=c.open_price,
                    high=c.high_price,
                    low=c.low_price,
                    close=c.close_price,
                    volume=getattr(c, "volume", 0) or 0,
                ).model_dump()
                for c in candles_raw
            ]
            return success_response(candles)
        except Exception as e:
            logger.debug(f"Broker price fetch failed: {e}")

    return success_response([])
