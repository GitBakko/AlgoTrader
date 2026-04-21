"""FX conversion — fail-loud.

Close-detection v2 must never silently accept a P&L value whose currency
differs from the account's without explicit conversion. The v1 code at
`Transaction.pl_value_in` logs a WARNING and returns the value unchanged,
which is exactly the silent FX drift the 2026-04-21 audit flagged.

This module replaces that behavior with a two-step contract:

1. ``normalize_currency(raw)``: strip broker-specific suffixes ("USDd" →
   "USD") so simple equality covers the common case. When the normalized
   currencies match there is nothing to convert and we return the amount
   unchanged.

2. ``FxConverter.convert(amount, from_ccy, to_ccy, at)``: genuine FX lookup
   via the existing ``FREDClient`` (FRED hosts the DEX* series of daily
   foreign-exchange rates, API-key-free path). If the required FRED series
   is unmapped, the API call fails, or the returned series is empty, raise
   :class:`FxUnavailableError`. The caller (``CloseDetector``) then keeps
   the row UNRECONCILED with an explicit reason — never a silent write.

Supported pairs cover every account / instrument currency we currently
trade (USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD). Additional pairs are
trivial to add — register them in :data:`FX_PAIR_SERIES`.

All rates are daily close. That is good enough for realized-P&L records
that land minutes after the close event; intraday granularity would
require a paid feed we do not need.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger


class FxError(Exception):
    """Base class for FX failures."""


class FxUnavailableError(FxError):
    """Raised when an FX rate cannot be obtained.

    Callers MUST treat this as reconciliation failure and persist the row
    with an explicit ``UNRECONCILED_FX_UNAVAILABLE`` reason, not with the
    unconverted value.
    """


# Mapping of (from_ccy, to_ccy) → (FRED series id, invert).
#
# Each FRED DEX* series expresses a specific direction; for the reverse
# direction we invert the quoted rate. Example:
#   DEXUSEU = "U.S. dollars to one euro" → rate expressed as USD per EUR.
#   → EUR→USD uses the rate as-is (invert=False).
#   → USD→EUR uses 1 / rate      (invert=True).
FX_PAIR_SERIES: dict[tuple[str, str], tuple[str, bool]] = {
    ("EUR", "USD"): ("DEXUSEU", False),
    ("USD", "EUR"): ("DEXUSEU", True),
    ("GBP", "USD"): ("DEXUSUK", False),
    ("USD", "GBP"): ("DEXUSUK", True),
    ("USD", "JPY"): ("DEXJPUS", False),
    ("JPY", "USD"): ("DEXJPUS", True),
    ("USD", "CAD"): ("DEXCAUS", False),
    ("CAD", "USD"): ("DEXCAUS", True),
    ("USD", "CHF"): ("DEXSZUS", False),
    ("CHF", "USD"): ("DEXSZUS", True),
    ("AUD", "USD"): ("DEXUSAL", False),
    ("USD", "AUD"): ("DEXUSAL", True),
    ("NZD", "USD"): ("DEXUSNZ", False),
    ("USD", "NZD"): ("DEXUSNZ", True),
}


def normalize_currency(raw: str | None) -> str:
    """Normalize a broker-reported currency string to an ISO 4217 code.

    Capital.com returns e.g. ``"USDd"`` on the demo account (the trailing
    ``d`` marks demo). Hyphens, lowercase variants and whitespace are all
    handled.

    Returns an uppercase 3-letter code, or the empty string if ``raw`` is
    falsy / impossible to parse.
    """
    if not raw:
        return ""
    cleaned = "".join(ch for ch in raw if ch.isalpha()).upper()
    # Strip demo / test suffixes: "USDD" → "USD" (Capital.com demo marker).
    while cleaned and len(cleaned) > 3 and cleaned.endswith("D"):
        cleaned = cleaned[:-1]
    return cleaned


@dataclass(slots=True)
class _CachedRate:
    rate: float
    fetched_at: datetime


class FxConverter:
    """Fail-loud FX conversion backed by FRED daily rates.

    Usage::

        fx = FxConverter()
        try:
            amount_in_usd = await fx.convert(29.28, "EUR", "USD")
        except FxUnavailableError as exc:
            # Leave reconciliation UNRECONCILED_FX_UNAVAILABLE
            ...
    """

    # In-process cache. The FRED series values change at most once per
    # business day, so a 12-hour TTL is plenty and avoids hammering FRED on
    # every close-detection tick.
    _CACHE_TTL_SECONDS = 12 * 60 * 60

    def __init__(self, fred_client=None):
        # Lazy import so unit tests can inject a stub without touching
        # SIL infrastructure.
        if fred_client is None:
            from src.external.fred_client import FREDClient

            fred_client = FREDClient()
        self._fred = fred_client
        self._cache: dict[str, _CachedRate] = {}

    async def convert(
        self,
        amount: float,
        from_ccy: str | None,
        to_ccy: str | None,
        at: datetime | None = None,
    ) -> float:
        """Convert ``amount`` from one currency to another, or raise.

        Args:
            amount: Value to convert, in ``from_ccy``.
            from_ccy: Source currency (any broker-string form; normalized).
            to_ccy: Target currency (same).
            at: Reserved for historical-rate support; currently unused,
                daily close is used.

        Raises:
            FxUnavailableError: if the pair is unmapped or the FRED
                lookup fails / returns no data.
        """
        del at  # documented for future historical extension
        src = normalize_currency(from_ccy)
        dst = normalize_currency(to_ccy)

        if not src or not dst:
            raise FxUnavailableError(
                f"FX normalize failed — from={from_ccy!r} to={to_ccy!r}"
            )
        if src == dst:
            return amount

        pair = (src, dst)
        if pair not in FX_PAIR_SERIES:
            raise FxUnavailableError(
                f"No FRED FX series registered for {src}->{dst}. "
                f"Extend FX_PAIR_SERIES in broker/fx.py before trading this pair."
            )

        series_id, invert = FX_PAIR_SERIES[pair]
        rate = await self._get_rate(series_id)
        if invert:
            if rate == 0:
                raise FxUnavailableError(
                    f"FRED series {series_id} returned zero rate — cannot invert for {src}->{dst}"
                )
            rate = 1.0 / rate
        converted = amount * rate
        logger.info(
            f"FX {src}->{dst}: {amount:.4f} * {rate:.6f} = {converted:.4f} "
            f"(series={series_id})"
        )
        return converted

    async def _get_rate(self, series_id: str) -> float:
        now = datetime.now(UTC)
        cached = self._cache.get(series_id)
        if cached and (now - cached.fetched_at).total_seconds() < self._CACHE_TTL_SECONDS:
            return cached.rate

        try:
            raw = await self._fred.fetch_single(series_id)
        except Exception as exc:  # noqa: BLE001 — surface as FX failure
            raise FxUnavailableError(
                f"FRED fetch_single({series_id!r}) raised: {exc}"
            ) from exc

        if raw is None:
            raise FxUnavailableError(
                f"FRED series {series_id!r} returned no value (unauthenticated, "
                f"empty dataset, or series gated behind API key)."
            )

        self._cache[series_id] = _CachedRate(rate=float(raw), fetched_at=now)
        return float(raw)


__all__ = [
    "FxConverter",
    "FxError",
    "FxUnavailableError",
    "FX_PAIR_SERIES",
    "normalize_currency",
]
