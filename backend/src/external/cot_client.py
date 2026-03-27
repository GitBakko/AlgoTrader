"""
Signal Intelligence Layer — COT (Commitment of Traders) Client.

Fetches weekly CFTC COT data via Nasdaq Data Link (ex-Quandl) API.
Data updates every Friday. TTL: 7 days.

Free tier: 50 API calls/day. No auth required for basic datasets.
"""

from datetime import UTC, datetime

from loguru import logger

from src.external.sil_base_client import SILBaseClient
from src.external.sil_schemas import COTData
from src.utils.config import get_settings

# MANTIS epic → CFTC contract code for Nasdaq Data Link
# Format: CFTC/{code}_FO_L_ALL for Futures-Only, Legacy, All
EPIC_TO_CONTRACT: dict[str, str] = {
    "XAUUSD": "088691",  # Gold - COMEX
    "XAGUSD": "084691",  # Silver - COMEX
    "WTIUSD": "067651",  # Crude Oil - NYMEX
    "EURUSD": "099741",  # Euro FX - CME
    "GBPUSD": "096742",  # British Pound - CME
    "USDJPY": "097741",  # Japanese Yen - CME
    "BTCUSD": "133741",  # Bitcoin - CME
    "US500": "13874A",  # E-mini S&P 500 - CME
    "NAS100": "209742",  # E-mini Nasdaq 100 - CME
    "NATGAS": "023651",  # Natural Gas - NYMEX
    "COPPER": "085692",  # Copper - COMEX
}

# Column indices in Nasdaq Data Link CFTC dataset
# Legacy format: [Date, Open Interest, Noncomm Long, Noncomm Short, ...]
COL_NONCOMM_LONG = 1
COL_NONCOMM_SHORT = 2


class COTClient(SILBaseClient):
    """CFTC Commitment of Traders data via Nasdaq Data Link."""

    BASE_URL = "https://data.nasdaq.com/api/v3/datasets/CFTC"

    def __init__(self, cache_ttl_minutes: int | None = None):
        super().__init__(
            "cot",
            cache_ttl_minutes=cache_ttl_minutes or 7 * 24 * 60,  # 7 days
        )

    @staticmethod
    def _auth_params() -> dict[str, str]:
        """Return API key param if configured."""
        key = get_settings().nasdaq_data_link_api_key
        return {"api_key": key} if key else {}

    async def fetch(self, epic: str) -> COTData:
        """
        Fetch COT data for a specific epic.

        Args:
            epic: MANTIS epic (e.g., "XAUUSD", "BTCUSD")

        Returns:
            COTData with positioning data. Defaults on failure.
        """
        contract = EPIC_TO_CONTRACT.get(epic)
        if contract is None:
            return COTData()

        cache_key = f"cot_{epic}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.BASE_URL}/{contract}_FO_L_ALL.json",
                params={
                    "rows": 5,
                    "order": "desc",
                    "column_index": f"{COL_NONCOMM_LONG},{COL_NONCOMM_SHORT}",
                    **self._auth_params(),
                },
            )
            resp.raise_for_status()
            dataset = resp.json().get("dataset", {})
            data_rows = dataset.get("data", [])

            if not data_rows:
                logger.debug(f"[COTClient] No data for {epic} ({contract})")
                return COTData()

            return self._parse_rows(data_rows, epic, cache_key)

        except Exception as e:
            logger.warning(f"[COTClient] Fetch failed for {epic}: {e}")
            return COTData()

    def _parse_rows(self, rows: list[list], epic: str, cache_key: str) -> COTData:
        """Parse COT data rows into COTData with z-score."""
        # Latest row: [date, noncomm_long, noncomm_short]
        latest = rows[0]
        report_date_str = latest[0] if isinstance(latest[0], str) else str(latest[0])

        try:
            report_date = datetime.strptime(report_date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            report_date = None

        noncomm_long = int(latest[1] or 0)
        noncomm_short = int(latest[2] or 0)
        net_position = noncomm_long - noncomm_short

        # Compute z-score over available weeks (up to 4)
        net_positions = []
        for row in rows:
            try:
                nl = int(row[1] or 0)
                ns = int(row[2] or 0)
                net_positions.append(nl - ns)
            except (ValueError, IndexError):
                pass

        z_score = self._compute_z_score(net_positions)

        # Normalize net position: simple ratio long/(long+short)
        total = noncomm_long + noncomm_short
        net_normalized = (noncomm_long / total * 2 - 1) if total > 0 else 0.0

        result = COTData(
            noncomm_long=noncomm_long,
            noncomm_short=noncomm_short,
            net_position=net_position,
            net_position_normalized=round(net_normalized, 4),
            is_institutional_bullish=net_position > 0,
            z_score_4w=round(z_score, 4),
            report_date=report_date,
        )
        self._set_cache(cache_key, result)
        logger.info(
            f"[COTClient] {epic}: net={net_position:+d}, "
            f"z={z_score:.2f}, bull={result.is_institutional_bullish}"
        )
        return result

    @staticmethod
    def _compute_z_score(values: list[int]) -> float:
        """Compute z-score of first value vs the series."""
        if len(values) < 2:
            return 0.0
        current = values[0]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        if variance <= 0:
            return 0.0
        std = variance**0.5
        return (current - mean) / std

    @staticmethod
    def supported_epics() -> list[str]:
        """Return list of epics with COT data available."""
        return list(EPIC_TO_CONTRACT.keys())
