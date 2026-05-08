"""
Markets API router.
Provides market search, OHLC price data, and market info.
Uses broker client when available, falls back to static data.
"""

from fastapi import APIRouter, Depends, Path, Query, Request
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.dependencies import get_broker_client, get_data_access, get_position_repo
from src.api.schemas import MarketInfo, OHLCResponse, error_response, success_response
from src.data.utils import calculate_next_market_open

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Static market list (fallback when no broker connection)
SUPPORTED_MARKETS = [
    # Existing 9 assets
    MarketInfo(epic="XAUUSD", name="Gold (XAU/USD)", change_pct=0.0),
    MarketInfo(epic="BTCUSD", name="Bitcoin (BTC/USD)", change_pct=0.0),
    MarketInfo(epic="US500", name="S&P 500 (US500)", change_pct=0.0),
    MarketInfo(epic="WTIUSD", name="Crude Oil WTI (WTI/USD)", change_pct=0.0),
    MarketInfo(epic="EURUSD", name="Euro / US Dollar (EUR/USD)", change_pct=0.0),
    MarketInfo(epic="NVDA", name="NVIDIA Corporation (NVDA)", change_pct=0.0),
    MarketInfo(epic="TSLA", name="Tesla Inc (TSLA)", change_pct=0.0),
    MarketInfo(epic="XAGUSD", name="Silver (XAG/USD)", change_pct=0.0),
    MarketInfo(epic="DE40", name="Germany 40 / DAX (DE40)", change_pct=0.0),
    # New 12 assets - Phase 12: Portfolio Expansion
    MarketInfo(epic="SOLUSD", name="Solana (SOL/USD)", change_pct=0.0),
    MarketInfo(epic="ETHUSD", name="Ethereum (ETH/USD)", change_pct=0.0),
    MarketInfo(epic="BNBUSD", name="Binance Coin (BNB/USD)", change_pct=0.0),
    MarketInfo(epic="DOGUSD", name="Dogecoin (DOGE/USD)", change_pct=0.0),
    MarketInfo(epic="DASHUSD", name="Dash (DASH/USD)", change_pct=0.0),
    MarketInfo(epic="ICPUSD", name="Internet Computer (ICP/USD)", change_pct=0.0),
    MarketInfo(epic="NATGAS", name="Natural Gas (NATGAS)", change_pct=0.0),
    MarketInfo(epic="COPPER", name="Copper (COPPER)", change_pct=0.0),
    MarketInfo(epic="PLATINUM", name="Platinum (PLATINUM)", change_pct=0.0),
    MarketInfo(epic="GBPUSD", name="British Pound / US Dollar (GBP/USD)", change_pct=0.0),
    MarketInfo(epic="USDJPY", name="US Dollar / Japanese Yen (USD/JPY)", change_pct=0.0),
    MarketInfo(epic="NAS100", name="Nasdaq 100 (US TECH 100)", change_pct=0.0),
    # Phase 14 stock candidates (2026-05-08 promoted)
    MarketInfo(epic="AAPL", name="Apple Inc (AAPL)", change_pct=0.0),
    MarketInfo(epic="MSFT", name="Microsoft Corp (MSFT)", change_pct=0.0),
    MarketInfo(epic="GOOGL", name="Alphabet Inc Class A (GOOGL)", change_pct=0.0),
    MarketInfo(epic="AMZN", name="Amazon.com Inc (AMZN)", change_pct=0.0),
    MarketInfo(epic="META", name="Meta Platforms (META)", change_pct=0.0),
    MarketInfo(epic="AMD", name="Advanced Micro Devices (AMD)", change_pct=0.0),
    # Phase 14 forex (2026-05-08/09)
    MarketInfo(epic="USDCHF", name="US Dollar / Swiss Franc (USD/CHF)", change_pct=0.0),
    MarketInfo(epic="USDCAD", name="US Dollar / Canadian Dollar (USD/CAD)", change_pct=0.0),
    MarketInfo(epic="AUDUSD", name="Australian Dollar / US Dollar (AUD/USD)", change_pct=0.0),
    MarketInfo(epic="NZDUSD", name="New Zealand Dollar / US Dollar (NZD/USD)", change_pct=0.0),
    MarketInfo(epic="EURJPY", name="Euro / Japanese Yen (EUR/JPY)", change_pct=0.0),
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
@limiter.limit("30/minute")  # Higher limit for read-only operations
async def search_markets(
    request: Request,
    q: str = Query(default="", min_length=0),
    broker=Depends(get_broker_client),
):
    """Search available markets by name or epic."""
    # Try broker search first
    if broker and q:
        try:

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
            m for m in SUPPORTED_MARKETS if query in m.epic.lower() or query in m.name.lower()
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

            res = (
                Resolution(resolution.upper())
                if resolution.upper() in _RESOLUTION_MAP
                else Resolution.HOUR
            )
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


@router.get("/{epic}/overnight-swap")
async def get_overnight_swap(
    epic: str = Path(...),
    broker=Depends(get_broker_client),
):
    """
    Overnight / rollover swap info for a Capital.com CFD epic.

    Dashboard v2 (D1:B) — replaces the Bybit-funding design that did not
    match our stack. Returns the broker-reported overnight financing
    rates when available, falling back to the backtest static table
    (src.backtest.costs.OVERNIGHT_RATES) so the tile always has a
    value to display.

    Response:
      {
        epic, currency,
        long_rate_daily, short_rate_daily,               # fractions of notional
        long_rate_pct, short_rate_pct,                   # human-readable %
        weekend_multiplier,                              # Capital.com 3x on Wed-night
        next_charge_utc,                                 # typical 22:00 UTC rollover
        source: "broker" | "static_fallback"
      }
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from src.backtest.costs import OVERNIGHT_RATES

    epic_upper = epic.upper()
    long_rate: float | None = None
    short_rate: float | None = None
    currency: str | None = None
    source = "static_fallback"
    raw_instrument: dict | None = None

    next_charge_ms: int | None = None
    swap_interval_min: int | None = None

    if broker is not None:
        try:
            details = await broker.get_market_details(epic_upper)
            if isinstance(details, dict):
                instrument = details.get("instrument") or {}
                raw_instrument = instrument
                currency = instrument.get("currency")
                # Capital.com market details expose overnight financing under
                # `overnightFee`: {longRate, shortRate, swapChargeTimestamp, swapChargeInterval}.
                # `longRate` / `shortRate` are already **percentages per interval**
                # (interval = swapChargeInterval minutes, typically 1440 = 1 day).
                fee = instrument.get("overnightFee")
                if isinstance(fee, dict):
                    lr = fee.get("longRate")
                    sr = fee.get("shortRate")
                    if isinstance(lr, (int, float)):
                        long_rate = float(lr)
                    if isinstance(sr, (int, float)):
                        short_rate = float(sr)
                    ts = fee.get("swapChargeTimestamp")
                    if isinstance(ts, (int, float)):
                        next_charge_ms = int(ts)
                    iv = fee.get("swapChargeInterval")
                    if isinstance(iv, (int, float)):
                        swap_interval_min = int(iv)
                if long_rate is not None or short_rate is not None:
                    source = "broker"
        except Exception as e:
            logger.debug(f"overnight swap broker lookup failed for {epic_upper}: {e}")

    # Fallback: static table backed by the backtest cost model.
    if long_rate is None or short_rate is None:
        static = OVERNIGHT_RATES.get(
            epic_upper, {"long": -0.000015, "short": -0.000010}
        )
        # Static values are stored as fractions; convert to percent to match broker.
        long_rate = long_rate if long_rate is not None else static["long"] * 100
        short_rate = short_rate if short_rate is not None else static["short"] * 100

    # Next charge: prefer broker-provided timestamp, fall back to 22:00 UTC.
    if next_charge_ms:
        next_charge = _dt.fromtimestamp(next_charge_ms / 1000, tz=_UTC)
    else:
        now = _dt.now(_UTC)
        next_charge = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if now >= next_charge:
            next_charge = next_charge + _td(days=1)

    # `long_rate` / `short_rate` are already in percent (per swapChargeInterval).
    # `*_daily` fields express the fraction equivalent (pct / 100).
    return success_response({
        "epic": epic_upper,
        "currency": currency or "USD",
        "long_rate_daily": round(long_rate / 100, 8),
        "short_rate_daily": round(short_rate / 100, 8),
        "long_rate_pct": round(long_rate, 6),
        "short_rate_pct": round(short_rate, 6),
        "swap_interval_minutes": swap_interval_min or 1440,
        "weekend_multiplier": 3,
        "next_charge_utc": next_charge.isoformat(),
        "source": source,
        "instrument_raw": raw_instrument if source == "broker" else None,
    })


@router.get("/{epic}/swap-accum")
async def get_swap_accum(
    epic: str = Path(...),
    days: int = Query(default=7, ge=1, le=90),
    broker=Depends(get_broker_client),
    position_repo=Depends(get_position_repo),
):
    """
    N-day accumulated overnight swap for an epic (Dashboard v2 Phase 4 §B).

    MINIMAL implementation — no historical snapshot table yet:
      - rate: current broker overnightFee (or static fallback)
      - notional: size × entry_price of the OLDEST open position on this epic
      - per-day expansion: applies Wed 3× multiplier where the rollover date
        falls on Wednesday UTC (Capital.com triple-swap convention)
    Returns 0 notional / empty per_day when no open position exists.

    Response:
      { epic, currency, period_days, total_accum,
        per_day: [{ date, rate_pct, notional, swap }], source }
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from src.backtest.costs import OVERNIGHT_RATES

    epic_upper = epic.upper()

    long_rate_pct: float | None = None
    short_rate_pct: float | None = None
    currency: str | None = None
    source = "static_fallback"

    if broker is not None:
        try:
            details = await broker.get_market_details(epic_upper)
            if isinstance(details, dict):
                instrument = details.get("instrument") or {}
                currency = instrument.get("currency")
                fee = instrument.get("overnightFee")
                if isinstance(fee, dict):
                    lr = fee.get("longRate")
                    sr = fee.get("shortRate")
                    if isinstance(lr, (int, float)):
                        long_rate_pct = float(lr)
                    if isinstance(sr, (int, float)):
                        short_rate_pct = float(sr)
                if long_rate_pct is not None or short_rate_pct is not None:
                    source = "broker"
        except Exception as e:
            logger.debug(f"swap-accum broker lookup failed for {epic_upper}: {e}")

    if long_rate_pct is None or short_rate_pct is None:
        static = OVERNIGHT_RATES.get(epic_upper, {"long": -0.000015, "short": -0.000010})
        if long_rate_pct is None:
            long_rate_pct = static["long"] * 100
        if short_rate_pct is None:
            short_rate_pct = static["short"] * 100

    # Resolve position notional + direction from DB (oldest OPEN row on this epic).
    position_size = 0.0
    position_entry = 0.0
    direction = "LONG"
    if position_repo is not None:
        try:
            positions = await position_repo.get_by_epic(epic_upper, status="OPEN")
            if positions:
                positions_sorted = sorted(
                    positions,
                    key=lambda p: p.opened_at or _dt.min,
                )
                pos = positions_sorted[0]
                position_size = float(pos.size or 0)
                position_entry = float(pos.entry_price or 0)
                direction = (pos.direction or "LONG").upper()
        except Exception as e:
            logger.debug(f"swap-accum position lookup for {epic_upper} failed: {e}")

    # Position.direction is stored as "SELL" / "BUY" on our rows but the
    # upstream broker model serializes it as "SHORT" / "LONG". Accept both.
    is_short = direction.upper() in ("SHORT", "SELL")
    rate_pct = short_rate_pct if is_short else long_rate_pct
    notional = position_size * position_entry if (position_size and position_entry) else 0.0

    # Load historical snapshot rows (one per epic-date) from DB. For any
    # day in the requested window without a row, fall back to the current
    # rate+notional computed above — same approximation as the MINIMAL
    # Phase 4 behaviour, so a fresh epic that has no history yet still
    # renders something reasonable while the scheduler fills rows over time.
    snapshot_by_date: dict[str, dict] = {}
    try:
        from src.database.repositories.swap_snapshot_repository import (
            SwapSnapshotRepository,
        )
        from src.database.session import DatabaseManager

        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            snap_repo = SwapSnapshotRepository(session)
            rows = await snap_repo.get_recent(epic_upper, days)
            for r in rows:
                r_dir = (r.direction or "").upper()
                snap_rate = (
                    r.short_rate_pct if r_dir in ("SHORT", "SELL")
                    else r.long_rate_pct
                )
                if snap_rate is None:
                    snap_rate = rate_pct
                snapshot_by_date[r.snapshot_date.isoformat()] = {
                    "rate_pct": float(snap_rate),
                    "notional": float(r.notional or 0),
                    "source": r.source,
                }
    except Exception as e:
        logger.debug(f"swap-accum snapshot DB lookup failed for {epic_upper}: {e}")

    # Build per-day series looking back (today-(days-1) .. today).
    today = _dt.now(_UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    per_day: list[dict] = []
    total = 0.0
    sources_used: set[str] = set()
    for i in range(days - 1, -1, -1):
        day = today - _td(days=i)
        day_key = day.strftime("%Y-%m-%d")
        # Capital.com convention: Wed rollover charges 3× (weekend anticipated).
        multiplier = 3 if day.weekday() == 2 else 1

        snap = snapshot_by_date.get(day_key)
        if snap is not None:
            day_rate = snap["rate_pct"]
            day_notional = snap["notional"]
            day_source = snap["source"]
        else:
            day_rate = rate_pct
            day_notional = notional
            day_source = source
        sources_used.add(day_source)

        day_swap = (day_rate / 100.0) * day_notional * multiplier
        total += day_swap
        per_day.append({
            "date": day_key,
            "rate_pct": round(day_rate, 6),
            "notional": round(day_notional, 2),
            "swap": round(day_swap, 4),
            "multiplier": multiplier,
            "source": day_source,
        })

    # Response-level source: "historical" when at least one day came from
    # a stored snapshot; otherwise echo the fallback source.
    if any(s in sources_used for s in ("broker", "static_fallback")) and (
        len(sources_used - {"broker", "static_fallback"}) == 0
    ):
        response_source = source
    else:
        response_source = "historical"

    return success_response({
        "epic": epic_upper,
        "currency": currency or "USD",
        "period_days": days,
        "total_accum": round(total, 2),
        "direction": direction if notional > 0 else None,
        "per_day": per_day,
        "source": response_source,
    })


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
            # Defensive: ensure details is a dict
            if not isinstance(details, dict):
                logger.warning(f"Broker returned non-dict response for {epic}: {type(details)}")
                raise ValueError(f"Unexpected response type: {type(details)}")
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
