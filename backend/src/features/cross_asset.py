"""
Cross-asset feature engine.

Computes rolling correlations, lead-lag returns, sector momentum,
and correlation regime detection across related assets.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from loguru import logger

from src.features.cross_asset_config import (
    CORR_REGIME_NORMAL_RANGE,
    CORR_REGIME_PANIC_THRESHOLD,
    CORRELATION_WINDOW_LONG,
    CORRELATION_WINDOW_SHORT,
    LEAD_LAG_WINDOWS,
    SECTOR_MOMENTUM_WINDOW,
)


class CrossAssetEngine:
    """Compute cross-asset features for ML models."""

    def compute_rolling_correlation(
        self,
        df_main: pl.DataFrame,
        df_related: pl.DataFrame,
        window: int,
    ) -> pl.DataFrame:
        """Rolling Pearson correlation of log returns between two assets.

        Parameters
        ----------
        df_main : pl.DataFrame
            Main asset with "close" column.
        df_related : pl.DataFrame
            Related asset with "close" column.
        window : int
            Rolling window size in bars.

        Returns
        -------
        pl.DataFrame
            ``df_main`` with an extra ``rolling_corr_{window}`` column.
        """
        main_close = df_main["close"].to_numpy(zero_copy_only=False).astype(np.float64)
        rel_close = df_related["close"].to_numpy(zero_copy_only=False).astype(np.float64)

        # Align to tail when lengths differ
        n = len(main_close)
        if len(rel_close) < n:
            pad = np.full(n - len(rel_close), np.nan)
            rel_close = np.concatenate([pad, rel_close])
        elif len(rel_close) > n:
            rel_close = rel_close[-n:]

        # Log returns
        main_ret = np.diff(np.log(np.abs(main_close) + 1e-12), prepend=np.nan)
        rel_ret = np.diff(np.log(np.abs(rel_close) + 1e-12), prepend=np.nan)

        corr = np.full(n, np.nan)
        for i in range(window, n):
            x = main_ret[i - window + 1 : i + 1]
            y = rel_ret[i - window + 1 : i + 1]
            mask = ~(np.isnan(x) | np.isnan(y))
            if mask.sum() < window // 2:
                continue
            xm = x[mask]
            ym = y[mask]
            if np.std(xm) < 1e-12 or np.std(ym) < 1e-12:
                continue
            corr[i] = np.corrcoef(xm, ym)[0, 1]

        col_name = f"rolling_corr_{window}"
        return df_main.with_columns(pl.Series(name=col_name, values=corr.tolist()))

    def compute_lead_lag_returns(
        self,
        df_related: pl.DataFrame,
        lags: list[int] | None = None,
    ) -> pl.DataFrame:
        """Lagged log returns from a related asset.

        Parameters
        ----------
        df_related : pl.DataFrame
            Related asset with "close" column.
        lags : list[int], optional
            List of lag periods. Defaults to ``LEAD_LAG_WINDOWS``.

        Returns
        -------
        pl.DataFrame
            ``df_related`` with ``ret_lag_{k}`` columns.
        """
        if lags is None:
            lags = LEAD_LAG_WINDOWS

        log_close = df_related["close"].log()
        result = df_related
        for lag in lags:
            col = log_close.diff(lag).alias(f"ret_lag_{lag}")
            result = result.with_columns(col)
        return result

    def compute_sector_momentum(
        self,
        cluster_dfs: dict[str, pl.DataFrame],
        window: int | None = None,
    ) -> pl.DataFrame:
        """Average rolling return and dispersion across a cluster.

        Parameters
        ----------
        cluster_dfs : dict[str, pl.DataFrame]
            Map of epic -> DataFrame with "close" and "timestamp" columns.
        window : int, optional
            Smoothing window. Defaults to ``SECTOR_MOMENTUM_WINDOW``.

        Returns
        -------
        pl.DataFrame
            DataFrame with ``sector_momentum_{window}`` and
            ``sector_dispersion_{window}`` columns, aligned to the
            first epic's timestamps.
        """
        if window is None:
            window = SECTOR_MOMENTUM_WINDOW

        if not cluster_dfs:
            raise ValueError("cluster_dfs must not be empty")

        # Collect log returns for each member, aligned to shortest length
        all_returns: list[np.ndarray] = []
        ref_key = next(iter(cluster_dfs))
        ref_df = cluster_dfs[ref_key]
        n = len(ref_df)

        for _epic, df in cluster_dfs.items():
            closes = df["close"].to_numpy(zero_copy_only=False).astype(np.float64)
            log_ret = np.diff(np.log(np.abs(closes) + 1e-12), prepend=np.nan)
            # Align to tail
            if len(log_ret) < n:
                pad = np.full(n - len(log_ret), np.nan)
                log_ret = np.concatenate([pad, log_ret])
            elif len(log_ret) > n:
                log_ret = log_ret[-n:]
            all_returns.append(log_ret)

        returns_matrix = np.column_stack(all_returns)

        # Average return across cluster at each bar
        with np.errstate(all="ignore"):
            avg_ret = np.nanmean(returns_matrix, axis=1)
            dispersion = np.nanstd(returns_matrix, axis=1)

        # Smooth with rolling mean via np.convolve
        kernel = np.ones(window) / window
        smoothed_mom = np.convolve(avg_ret, kernel, mode="full")[:n]
        smoothed_mom[:window] = np.nan

        smoothed_disp = np.convolve(dispersion, kernel, mode="full")[:n]
        smoothed_disp[:window] = np.nan

        mom_col = f"sector_momentum_{window}"
        disp_col = f"sector_dispersion_{window}"

        return pl.DataFrame(
            {
                "timestamp": ref_df["timestamp"],
                mom_col: smoothed_mom.tolist(),
                disp_col: smoothed_disp.tolist(),
            }
        )

    def build_cross_asset_features(
        self,
        main_df: pl.DataFrame,
        epic: str,
        related_dfs: dict[str, pl.DataFrame],
    ) -> pl.DataFrame:
        """Build all cross-asset features for one epic.

        Parameters
        ----------
        main_df : pl.DataFrame
            Main asset OHLCV data.
        epic : str
            Epic name (used for logging only).
        related_dfs : dict[str, pl.DataFrame]
            Map of related epic -> OHLCV DataFrame.

        Returns
        -------
        pl.DataFrame
            ``main_df`` with cross-asset feature columns appended.
        """
        if not related_dfs:
            logger.debug("No related assets for {}, skipping cross-asset", epic)
            return main_df

        result = main_df.clone()

        for rel_epic, rel_df in related_dfs.items():
            tag = rel_epic.lower().replace("usd", "").replace("500", "sp5")

            # Rolling correlations (short + long)
            for win in (CORRELATION_WINDOW_SHORT, CORRELATION_WINDOW_LONG):
                corr_df = self.compute_rolling_correlation(main_df, rel_df, window=win)
                src_col = f"rolling_corr_{win}"
                dst_col = f"corr_{tag}_{win}"
                result = result.with_columns(corr_df[src_col].alias(dst_col))

            # Lead-lag returns
            lag_df = self.compute_lead_lag_returns(rel_df, lags=LEAD_LAG_WINDOWS)
            n_main = len(main_df)
            for lag in LEAD_LAG_WINDOWS:
                src_col = f"ret_lag_{lag}"
                dst_col = f"lead_{tag}_lag{lag}"
                vals = lag_df[src_col].to_numpy(zero_copy_only=False).astype(np.float64)
                # Align to tail
                if len(vals) < n_main:
                    pad = np.full(n_main - len(vals), np.nan)
                    vals = np.concatenate([pad, vals])
                elif len(vals) > n_main:
                    vals = vals[-n_main:]
                result = result.with_columns(pl.Series(name=dst_col, values=vals.tolist()))

        # Sector momentum if we have 2+ related assets
        if len(related_dfs) >= 2:
            mom_df = self.compute_sector_momentum(related_dfs, window=SECTOR_MOMENTUM_WINDOW)
            n_main = len(main_df)
            for col in mom_df.columns:
                if col == "timestamp":
                    continue
                vals = mom_df[col].to_numpy(zero_copy_only=False).astype(np.float64)
                if len(vals) < n_main:
                    pad = np.full(n_main - len(vals), np.nan)
                    vals = np.concatenate([pad, vals])
                elif len(vals) > n_main:
                    vals = vals[-n_main:]
                result = result.with_columns(pl.Series(name=col, values=vals.tolist()))

        n_cross = len([c for c in result.columns if c not in main_df.columns])
        logger.debug("Built {} cross-asset features for {}", n_cross, epic)
        return result

    def compute_correlation_regime(
        self,
        all_dfs: dict[str, pl.DataFrame],
        window: int = 50,
    ) -> pl.DataFrame:
        """Detect correlation regime from pairwise rolling correlations.

        Parameters
        ----------
        all_dfs : dict[str, pl.DataFrame]
            Map of epic -> DataFrame with "close" and "timestamp" columns.
        window : int
            Rolling window for correlation computation.

        Returns
        -------
        pl.DataFrame
            DataFrame with ``mean_correlation`` and ``correlation_regime``
            columns, indexed by the first asset's timestamps.
        """
        keys = list(all_dfs.keys())
        if len(keys) < 2:
            raise ValueError("Need at least 2 assets for regime detection")

        ref_key = keys[0]
        ref_df = all_dfs[ref_key]
        n = len(ref_df)

        # Collect log returns for all assets, aligned to n
        returns_list: list[np.ndarray] = []
        for key in keys:
            closes = all_dfs[key]["close"].to_numpy(zero_copy_only=False).astype(np.float64)
            log_ret = np.diff(np.log(np.abs(closes) + 1e-12), prepend=np.nan)
            if len(log_ret) < n:
                pad = np.full(n - len(log_ret), np.nan)
                log_ret = np.concatenate([pad, log_ret])
            elif len(log_ret) > n:
                log_ret = log_ret[-n:]
            returns_list.append(log_ret)

        num_assets = len(keys)
        mean_corr = np.full(n, np.nan)

        for i in range(window, n):
            # Extract window slice for each asset
            slices = []
            for ret in returns_list:
                s = ret[i - window + 1 : i + 1]
                slices.append(s)
            mat = np.column_stack(slices)

            # Drop rows with any NaN
            mask = ~np.any(np.isnan(mat), axis=1)
            if mask.sum() < window // 2:
                continue
            mat_clean = mat[mask]

            # Pairwise correlation matrix
            corr_mat = np.corrcoef(mat_clean, rowvar=False)

            # Mean of upper triangle (excluding diagonal)
            upper_idx = np.triu_indices(num_assets, k=1)
            upper_vals = corr_mat[upper_idx]
            mean_corr[i] = np.nanmean(upper_vals)

        # Classify regime
        elevated_threshold = CORR_REGIME_NORMAL_RANGE[1]  # 0.55
        normal_low = CORR_REGIME_NORMAL_RANGE[0]  # 0.20

        regimes: list[str | None] = []
        for mc in mean_corr:
            if np.isnan(mc):
                regimes.append(None)
            elif mc >= CORR_REGIME_PANIC_THRESHOLD:
                regimes.append("panic")
            elif mc >= elevated_threshold:
                regimes.append("elevated")
            elif mc >= normal_low:
                regimes.append("normal")
            else:
                regimes.append("decorrelated")

        return pl.DataFrame(
            {
                "timestamp": ref_df["timestamp"],
                "mean_correlation": mean_corr.tolist(),
                "correlation_regime": regimes,
            }
        )
