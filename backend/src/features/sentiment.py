"""
Sentiment-based feature engineering.
Adds 5 sentiment features from external APIs (Finnhub + Marketaux):
1. insider_mspr - Monthly Share Purchase Ratio from insider trading
2. analyst_consensus - Buy/Hold/Sell consensus (-1, 0, 1)
3. price_target_upside - % upside to analyst target price
4. earnings_flag - Binary flag for upcoming earnings (7 days)
5. news_sentiment_avg - Rolling 7-day news sentiment average
"""

from datetime import datetime, timedelta

import polars as pl
from loguru import logger

from src.external.models import (
    AnalystConsensus,
    Earnings,
    InsiderSentiment,
    NewsArticle,
    PriceTarget,
)


class SentimentFeatures:
    """
    Sentiment-based feature engineering (pattern similar to TechnicalIndicators).

    All methods are static and return a modified DataFrame with new columns.
    Gracefully handles missing data by filling with default values (0 or None).
    """

    @staticmethod
    def add_insider_mspr(df: pl.DataFrame, insider_data: list[InsiderSentiment]) -> pl.DataFrame:
        """
        Add insider MSPR feature (Monthly Share Purchase Ratio).

        MSPR indicates whether insiders are buying (positive) or selling (negative).
        Uses asof join to forward-fill values for up to 30 days.

        Args:
            df: DataFrame with timestamp column
            insider_data: List of insider sentiment entries

        Returns:
            DataFrame with 'insider_mspr' column added
        """
        if not insider_data:
            logger.debug("No insider data, setting insider_mspr to None")
            return df.with_columns(pl.lit(None).alias("insider_mspr").cast(pl.Float64))

        # Create DataFrame with timestamp from period (mid-month assumption)
        insider_df = pl.DataFrame(
            [
                {
                    "timestamp": datetime.strptime(d.period + "-15", "%Y-%m-%d"),
                    "insider_mspr": d.mspr,
                }
                for d in insider_data
            ]
        )

        # Asof join (backward strategy = forward-fill in time)
        df = df.sort("timestamp").join_asof(insider_df, on="timestamp", strategy="backward")

        logger.debug(f"Added insider_mspr column ({len(insider_data)} data points)")
        return df

    @staticmethod
    def add_analyst_consensus(df: pl.DataFrame, analyst: AnalystConsensus | None) -> pl.DataFrame:
        """
        Add analyst consensus as categorical feature.

        Maps consensus to integer:
        - BUY → 1
        - HOLD → 0
        - SELL → -1

        Args:
            df: DataFrame
            analyst: Analyst consensus data

        Returns:
            DataFrame with 'analyst_consensus' column added
        """
        if analyst is None:
            value = 0
        elif analyst.consensus == "BUY":
            value = 1
        elif analyst.consensus == "SELL":
            value = -1
        else:
            value = 0

        df = df.with_columns(pl.lit(value).alias("analyst_consensus"))
        logger.debug(
            f"Added analyst_consensus: {value} ({analyst.consensus if analyst else 'HOLD'})"
        )
        return df

    @staticmethod
    def add_price_target_upside(df: pl.DataFrame, price_target: PriceTarget | None) -> pl.DataFrame:
        """
        Add analyst price target upside percentage.

        Upside % = (target_price - current_price) / current_price * 100

        Args:
            df: DataFrame
            price_target: Price target data

        Returns:
            DataFrame with 'price_target_upside' column added
        """
        if price_target is None:
            df = df.with_columns(pl.lit(0.0).alias("price_target_upside"))
            logger.debug("No price target, setting price_target_upside to 0.0")
            return df

        if price_target.current_price <= 0:
            logger.warning(
                f"Price target has invalid current_price={price_target.current_price}, "
                "setting upside to 0.0"
            )
            upside = 0.0
        else:
            upside = (
                (price_target.target_price - price_target.current_price)
                / price_target.current_price
                * 100.0
            )

        df = df.with_columns(pl.lit(upside).alias("price_target_upside"))
        logger.debug(f"Added price_target_upside: {upside:.2f}%")
        return df

    @staticmethod
    def add_earnings_flag(df: pl.DataFrame, earnings: list[Earnings]) -> pl.DataFrame:
        """
        Add binary flag for upcoming earnings within next 7 days.

        Flag = 1 if earnings event in next 7 days, 0 otherwise.

        Args:
            df: DataFrame with timestamp column
            earnings: List of earnings events

        Returns:
            DataFrame with 'earnings_flag' column added
        """
        if not earnings:
            logger.debug("No earnings data, setting earnings_flag to 0")
            return df.with_columns(pl.lit(0).alias("earnings_flag"))

        def has_earnings_soon(timestamp: datetime) -> int:
            """Check if any earnings event is within 7 days of timestamp."""
            for e in earnings:
                days_until = (e.date - timestamp).days
                if 0 <= days_until <= 7:
                    return 1
            return 0

        df = df.with_columns(
            pl.col("timestamp")
            .map_elements(has_earnings_soon, return_dtype=pl.Int32)
            .alias("earnings_flag")
        )

        logger.debug(f"Added earnings_flag ({len(earnings)} events tracked)")
        return df

    @staticmethod
    def add_news_sentiment(
        df: pl.DataFrame, news: list[NewsArticle], window_days: int = 7
    ) -> pl.DataFrame:
        """
        Add rolling average news sentiment.

        Calculates mean sentiment score from news published in the past N days.

        Args:
            df: DataFrame with timestamp column
            news: List of news articles
            window_days: Rolling window size in days

        Returns:
            DataFrame with 'news_sentiment_avg' column added
        """
        if not news:
            logger.debug("No news data, setting news_sentiment_avg to 0.0")
            return df.with_columns(pl.lit(0.0).alias("news_sentiment_avg"))

        # Create news DataFrame
        news_df = pl.DataFrame(
            [{"timestamp": a.published_at, "sentiment": a.sentiment} for a in news]
        )

        def rolling_sentiment(timestamp: datetime) -> float:
            """Calculate mean sentiment for news in window before timestamp."""
            cutoff = timestamp - timedelta(days=window_days)
            relevant = news_df.filter(
                (pl.col("timestamp") >= cutoff) & (pl.col("timestamp") <= timestamp)
            )
            if relevant.height == 0:
                return 0.0
            return relevant["sentiment"].mean()

        df = df.with_columns(
            pl.col("timestamp")
            .map_elements(rolling_sentiment, return_dtype=pl.Float64)
            .alias("news_sentiment_avg")
        )

        logger.debug(f"Added news_sentiment_avg ({len(news)} articles, {window_days}d window)")
        return df
