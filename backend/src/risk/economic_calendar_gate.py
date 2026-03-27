"""
Signal Intelligence Layer — Economic Calendar Gate.

Blocks trading during high-impact economic event windows.
Uses Finnhub /calendar/economic endpoint.
Configurable blackout window: ±N minutes around events.
"""

from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from src.external.sil_schemas import CalendarEvent
from src.utils.config import get_settings

# High-impact event keywords to match
HIGH_IMPACT_EVENTS = {
    "CPI",
    "Core CPI",
    "Consumer Price Index",
    "NFP",
    "Non-Farm Payrolls",
    "Nonfarm Payrolls",
    "FOMC",
    "Fed Rate Decision",
    "Federal Funds Rate",
    "GDP",
    "Gross Domestic Product",
    "PPI",
    "Producer Price Index",
    "ECB Rate Decision",
    "ECB Interest Rate",
    "BOE Rate Decision",
    "BOE Interest Rate",
    "BOJ Rate Decision",
    "Initial Jobless Claims",
    "Retail Sales",
    "Unemployment Rate",
    "ISM Manufacturing PMI",
    "ISM Services PMI",
}

# Currency sensitivity per epic
# USD → all high-impact US events
# EUR → ECB events
# GBP → BOE events
# JPY → BOJ events
# USD_MAJOR → only Fed Rate + CPI (reduced sensitivity for crypto)
EPIC_CURRENCIES: dict[str, list[str]] = {
    "XAUUSD": ["USD"],
    "XAGUSD": ["USD"],
    "EURUSD": ["USD", "EUR"],
    "GBPUSD": ["USD", "GBP"],
    "USDJPY": ["USD", "JPY"],
    "BTCUSD": ["USD_MAJOR"],
    "ETHUSD": ["USD_MAJOR"],
    "SOLUSD": ["USD_MAJOR"],
    "BNBUSD": ["USD_MAJOR"],
    "DOGUSD": ["USD_MAJOR"],
    "DASHUSD": ["USD_MAJOR"],
    "ICPUSD": ["USD_MAJOR"],
    "US500": ["USD"],
    "NAS100": ["USD"],
    "DE40": ["EUR"],
    "NVDA": ["USD"],
    "TSLA": ["USD"],
    "WTIUSD": ["USD"],
    "NATGAS": ["USD"],
    "COPPER": ["USD"],
    "PLATINUM": ["USD"],
}

# USD_MAJOR events (reduced set for crypto)
USD_MAJOR_EVENTS = {
    "Fed Rate Decision",
    "Federal Funds Rate",
    "FOMC",
    "CPI",
    "Core CPI",
    "Consumer Price Index",
}

# Currency → country code mapping for Finnhub
CURRENCY_COUNTRY: dict[str, str] = {
    "USD": "US",
    "EUR": "EU",  # or "DE", "FR" etc.
    "GBP": "GB",
    "JPY": "JP",
}


class EconomicCalendarGate:
    """
    Gates trading during high-impact economic event windows.

    Call `is_blackout(epic)` before executing a trade.
    Returns (True, reason) if in blackout window, (False, "") otherwise.
    """

    FINNHUB_URL = "https://finnhub.io/api/v1/calendar/economic"

    def __init__(self):
        self._settings = get_settings()
        self._events_cache: list[CalendarEvent] = []
        self._cache_date: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def is_blackout(
        self,
        epic: str,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        """
        Check if epic is in economic event blackout window.

        Args:
            epic: MANTIS epic (e.g., "XAUUSD")
            now: Current UTC time (defaults to now)

        Returns:
            (is_blackout, reason) tuple.
        """
        if not self._settings.sil_calendar_gate_enabled:
            return False, ""

        now = now or datetime.now(timezone.utc)
        events = await self._get_todays_events(now)

        minutes_before = self._settings.sil_calendar_minutes_before
        minutes_after = self._settings.sil_calendar_minutes_after
        currencies = EPIC_CURRENCIES.get(epic, [])

        if not currencies:
            return False, ""

        for event in events:
            if event.event_time is None:
                continue

            # Check if event is high-impact
            if not self._is_high_impact(event.event):
                continue

            # Check currency sensitivity
            if not self._affects_epic(event, currencies):
                continue

            # Check time window
            window_start = event.event_time - timedelta(minutes=minutes_before)
            window_end = event.event_time + timedelta(minutes=minutes_after)

            if window_start <= now <= window_end:
                time_str = event.event_time.strftime("%H:%M UTC")
                return True, (
                    f"Calendar blackout: {event.event} ({event.country}) "
                    f"at {time_str} [window: -{minutes_before}/+{minutes_after}min]"
                )

        return False, ""

    async def _get_todays_events(self, now: datetime) -> list[CalendarEvent]:
        """Get today's events, cached per day."""
        today_str = now.strftime("%Y-%m-%d")

        if self._cache_date == today_str and self._events_cache:
            return self._events_cache

        try:
            events = await self._fetch_events(today_str)
            self._events_cache = events
            self._cache_date = today_str
            high_impact = [e for e in events if self._is_high_impact(e.event)]
            logger.info(
                f"[CalendarGate] Loaded {len(events)} events for {today_str}, "
                f"{len(high_impact)} high-impact"
            )
            return events
        except Exception as e:
            logger.warning(f"[CalendarGate] Failed to fetch events: {e}")
            return self._events_cache  # Return stale cache if available

    async def _fetch_events(self, date_str: str) -> list[CalendarEvent]:
        """Fetch economic events from Finnhub."""
        api_key = self._settings.finnhub_api_key
        if not api_key:
            logger.debug("[CalendarGate] No Finnhub API key")
            return []

        client = await self._get_client()
        resp = await client.get(
            self.FINNHUB_URL,
            params={
                "from": date_str,
                "to": date_str,
                "token": api_key,
            },
        )
        resp.raise_for_status()
        raw_events = resp.json().get("economicCalendar", [])

        events: list[CalendarEvent] = []
        for raw in raw_events:
            try:
                # Finnhub returns time as ISO string or just date
                time_str = raw.get("time", "")
                event_time = None
                if time_str:
                    try:
                        event_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass

                events.append(
                    CalendarEvent(
                        event=raw.get("event", ""),
                        country=raw.get("country", ""),
                        currency=raw.get("currency", ""),
                        impact=raw.get("impact", "low"),
                        event_time=event_time,
                        actual=(
                            str(raw.get("actual", "")) if raw.get("actual") is not None else None
                        ),
                        forecast=(
                            str(raw.get("estimate", ""))
                            if raw.get("estimate") is not None
                            else None
                        ),
                        previous=str(raw.get("prev", "")) if raw.get("prev") is not None else None,
                    )
                )
            except Exception:
                pass  # Skip malformed events

        return events

    @staticmethod
    def _is_high_impact(event_name: str) -> bool:
        """Check if event name matches any high-impact event."""
        event_lower = event_name.lower()
        for hi_event in HIGH_IMPACT_EVENTS:
            if hi_event.lower() in event_lower:
                return True
        return False

    @staticmethod
    def _affects_epic(event: CalendarEvent, currencies: list[str]) -> bool:
        """Check if an economic event affects the given currencies."""
        event_country = event.country.upper()

        for currency in currencies:
            if currency == "USD_MAJOR":
                # Only Fed Rate + CPI for crypto
                if event_country == "US" and any(
                    kw.lower() in event.event.lower() for kw in USD_MAJOR_EVENTS
                ):
                    return True
            else:
                expected_country = CURRENCY_COUNTRY.get(currency)
                if expected_country and event_country == expected_country:
                    return True

        return False

    def get_cached_events(self) -> list[CalendarEvent]:
        """Return cached events (for API status endpoint)."""
        return self._events_cache

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
