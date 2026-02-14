"""
Markets API router.
Provides market search, OHLC price data, and market info.
Uses broker client when available, falls back to static data.
"""

from fastapi import APIRouter, Depends, Path, Query
from loguru import logger

from src.api.dependencies import get_broker_client, get_data_access
from src.api.schemas import MarketInfo, OHLCResponse, error_response, success_response
from src.data.utils import calculate_next_market_open

router = APIRouter()

# Static market list (fallback when no broker connection)
SUPPORTED_MARKETS = [
    MarketInfo(epic="XAUUSD", name="Gold (XAU/USD)", change_pct=0.0),
    MarketInfo(epic="BTCUSD", name="Bitcoin (BTC/USD)", change_pct=0.0),
    MarketInfo(epic="US500", name="S&P 500 (US500)", change_pct=0.0),
    MarketInfo(epic="WTIUSD", name="Crude Oil WTI (WTI/USD)", change_pct=0.0),
    MarketInfo(epic="EURUSD", name="Euro / US Dollar (EUR/USD)", change_pct=0.0),
    MarketInfo(epic="NVDA", name="NVIDIA Corporation (NVDA)", change_pct=0.0),
    MarketInfo(epic="TSLA", name="Tesla Inc (TSLA)", change_pct=0.0),
    MarketInfo(epic="XAGUSD", name="Silver (XAG/USD)", change_pct=0.0),
    MarketInfo(epic="DE40", name="Germany 40 / DAX (DE40)", change_pct=0.0),
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


@router.get("/status/{epic}")
async def get_market_status(
    epic: str = Path(..., description="Asset symbol (e.g., XAUUSD, BTCUSD)"),
    broker=Depends(get_broker_client),
):
    """
    Get market status with open/closed info and next open time.

    Returns market hours info from Capital.com broker:
    - is_open: bool (market currently open)
    - status: TRADEABLE | CLOSED | SUSPENDED
    - next_open: timestamp in ms (if closed)
    - session: {open, close, timezone}

    Example response:
        {
            "success": true,
            "data": {
                "epic": "XAUUSD",
                "is_open": false,
                "status": "CLOSED",
                "next_open": 1707868800000,
                "session": {
                    "open": "23:00",
                    "close": "22:00",
                    "timezone": "UTC"
                }
            }
        }
    """
    # Try to get market details from broker
    try:
        if broker:
            details = await broker.get_market_details(epic)
            market_status = details.get("snapshot", {}).get("marketStatus", "TRADEABLE")
            is_open = market_status == "TRADEABLE"

            # Calculate next open time if market is closed
            next_open = None
            if not is_open:
                next_open = calculate_next_market_open(epic)

            # Extract session info
            dealing_rules = details.get("dealingRules", {})
            market_order_pref = dealing_rules.get("marketOrderPreference", {})

            return success_response(
                {
                    "epic": epic,
                    "is_open": is_open,
                    "status": market_status,
                    "next_open": next_open,
                    "session": {
                        "open": market_order_pref.get("openingTime"),
                        "close": market_order_pref.get("closingTime"),
                        "timezone": details.get("snapshot", {}).get("updateTime", "UTC"),
                    },
                }
            )
    except Exception as e:
        logger.warning(f"Broker market status failed for {epic}: {e}")

    # Fallback: use simplified local logic
    from datetime import datetime
    from src.data.utils import is_market_hours

    now = datetime.now()
    is_open = is_market_hours(now, epic)
    next_open = None if is_open else calculate_next_market_open(epic)

    return success_response(
        {
            "epic": epic,
            "is_open": is_open,
            "status": "TRADEABLE" if is_open else "CLOSED",
            "next_open": next_open,
            "session": {
                "open": "00:00" if epic == "BTCUSD" else "Sunday 23:00",
                "close": "00:00" if epic == "BTCUSD" else "Friday 22:00",
                "timezone": "UTC",
            },
        }
    )
