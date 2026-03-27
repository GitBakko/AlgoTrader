"""
Macro data client: VIX, DXY, 10Y yield via yfinance.

Provides daily macro indicators for feature engineering.
Caches to Parquet for fast reload. Graceful degradation if yfinance unavailable.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
from loguru import logger

# Yahoo Finance tickers for macro indicators
MACRO_TICKERS = {
    "vix": "^VIX",
    "dxy": "DX-Y.NYB",
    "yield_10y": "^TNX",
}

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "macro"


class MacroDataClient:
    """
    Fetches and caches macro economic indicators (VIX, DXY, 10Y yield).

    Data is daily granularity. For intraday features, use asof join
    with strategy="backward" to align with hourly bars.
    """

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or _CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self.cache_dir / "macro_daily.parquet"

    def get_macro_data(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        force_refresh: bool = False,
    ) -> pl.DataFrame:
        """
        Get macro data (VIX, DXY, 10Y yield) as a Polars DataFrame.

        Columns: date, vix_close, vix_change_5d, dxy_close, dxy_change_5d, yield_10y_close

        Args:
            start_date: Start date for data
            end_date: End date for data
            force_refresh: If True, bypass cache and re-download

        Returns:
            DataFrame with macro columns. Returns empty-ish DataFrame on failure.
        """
        # Try cache first
        if not force_refresh and self._cache_file.exists():
            try:
                cached = pl.read_parquet(self._cache_file)
                if not cached.is_empty():
                    # Check if cache is fresh enough (< 24h old)
                    cache_mtime = datetime.fromtimestamp(
                        self._cache_file.stat().st_mtime, tz=timezone.utc
                    )
                    if (datetime.now(timezone.utc) - cache_mtime).total_seconds() < 86400:
                        return self._filter_dates(cached, start_date, end_date)
            except Exception as e:
                logger.debug(f"Macro cache read failed: {e}")

        # Fetch fresh data
        df = self._download_macro_data(start_date, end_date)

        # Cache if we got data
        if not df.is_empty():
            try:
                df.write_parquet(self._cache_file)
                logger.info(f"Cached macro data: {len(df)} rows")
            except Exception as e:
                logger.debug(f"Macro cache write failed: {e}")

        return df

    def _download_macro_data(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> pl.DataFrame:
        """Download macro data from yfinance."""
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed, returning empty macro data")
            return self._empty_macro_df()

        _start = start_date or (datetime.now() - timedelta(days=365 * 2))
        _end = end_date or datetime.now()

        start_str = _start.strftime("%Y-%m-%d")
        end_str = _end.strftime("%Y-%m-%d")

        frames = {}
        for name, ticker in MACRO_TICKERS.items():
            try:
                data = yf.download(
                    ticker,
                    start=start_str,
                    end=end_str,
                    progress=False,
                    auto_adjust=True,
                )
                if data is not None and not data.empty:
                    # yfinance returns pandas — convert to polars
                    pdf = data.reset_index()[["Date", "Close"]].copy()
                    pdf.columns = ["date", f"{name}_close"]
                    frames[name] = pl.from_pandas(pdf)
                    logger.info(f"Downloaded {name}: {len(pdf)} rows")
                else:
                    logger.warning(f"No data for {ticker}")
            except Exception as e:
                logger.warning(f"Failed to download {ticker}: {e}")

        if not frames:
            return self._empty_macro_df()

        # Merge all indicators on date
        result = None
        for name, df in frames.items():
            df = df.with_columns(pl.col("date").cast(pl.Date))
            if result is None:
                result = df
            else:
                result = result.join(df, on="date", how="outer_coalesce")

        if result is None:
            return self._empty_macro_df()

        # Sort by date and forward-fill for weekends/holidays
        result = result.sort("date")
        for col in result.columns:
            if col != "date":
                result = result.with_columns(pl.col(col).forward_fill())

        # Add 5-day change columns
        for name in MACRO_TICKERS:
            close_col = f"{name}_close"
            change_col = f"{name}_change_5d"
            if close_col in result.columns:
                result = result.with_columns(
                    (
                        (pl.col(close_col) - pl.col(close_col).shift(5))
                        / pl.col(close_col).shift(5)
                    ).alias(change_col)
                )

        # Fill any remaining NaN with 0
        result = result.fill_null(0.0)
        result = result.fill_nan(0.0)

        return result

    def _filter_dates(
        self,
        df: pl.DataFrame,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> pl.DataFrame:
        """Filter cached DataFrame by date range."""
        if start_date is not None:
            start_d = start_date.date() if hasattr(start_date, "date") else start_date
            df = df.filter(pl.col("date") >= start_d)
        if end_date is not None:
            end_d = end_date.date() if hasattr(end_date, "date") else end_date
            df = df.filter(pl.col("date") <= end_d)
        return df

    def _empty_macro_df(self) -> pl.DataFrame:
        """Return an empty DataFrame with the expected schema."""
        return pl.DataFrame(
            {
                "date": pl.Series([], dtype=pl.Date),
                "vix_close": pl.Series([], dtype=pl.Float64),
                "vix_change_5d": pl.Series([], dtype=pl.Float64),
                "dxy_close": pl.Series([], dtype=pl.Float64),
                "dxy_change_5d": pl.Series([], dtype=pl.Float64),
                "yield_10y_close": pl.Series([], dtype=pl.Float64),
                "yield_10y_change_5d": pl.Series([], dtype=pl.Float64),
            }
        )
