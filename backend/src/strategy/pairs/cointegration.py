"""
Cointegration analysis for pairs trading.
Uses numpy/scipy for ADF test and hedge ratio computation (no statsmodels).
"""

import numpy as np
from pydantic import BaseModel


class CointegrationResult(BaseModel):
    """Result of a cointegration test between two price series."""

    is_cointegrated: bool
    adf_statistic: float
    p_value_approx: float
    hedge_ratio: float
    half_life: float
    spread_mean: float
    spread_std: float


class CointegrationAnalyzer:
    """
    ADF test and cointegration analysis using numpy/scipy.
    Implements Engle-Granger two-step approach without statsmodels.
    """

    @staticmethod
    def _ols_regression(y: np.ndarray, x: np.ndarray) -> tuple[float, float, np.ndarray]:
        """
        Simple OLS regression: y = alpha + beta * x + residuals.

        Returns:
            (alpha, beta, residuals)
        """
        n = len(x)
        x_with_const = np.column_stack([np.ones(n), x])
        # Normal equation: (X'X)^-1 X'y
        try:
            coeffs = np.linalg.lstsq(x_with_const, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return 0.0, 0.0, y.copy()

        alpha, beta = coeffs[0], coeffs[1]
        residuals = y - (alpha + beta * x)
        return alpha, beta, residuals

    @staticmethod
    def _adf_test(series: np.ndarray, max_lag: int = 1) -> tuple[float, float]:
        """
        Augmented Dickey-Fuller test (simplified).

        Tests H0: series has a unit root (non-stationary).
        Returns (adf_statistic, approximate_p_value).

        Uses MacKinnon critical values approximation for p-value.
        """
        n = len(series)
        if n < 20:
            return 0.0, 1.0

        # First difference
        dy = np.diff(series)
        y_lag = series[:-1]

        # Regression: dy = alpha + gamma * y_lag + eps
        n_dy = len(dy)
        x_mat = np.column_stack([np.ones(n_dy), y_lag])

        # Add lagged differences if max_lag > 0
        if max_lag > 0:
            for lag in range(1, min(max_lag + 1, n_dy)):
                lagged_dy = np.zeros(n_dy)
                lagged_dy[lag:] = dy[:-lag] if lag < len(dy) else 0
                x_mat = np.column_stack([x_mat, lagged_dy])

        try:
            coeffs, residuals_sum, _, _ = np.linalg.lstsq(x_mat, dy, rcond=None)
        except np.linalg.LinAlgError:
            return 0.0, 1.0

        gamma = coeffs[1]  # Coefficient on y_lag

        # Standard error of gamma
        residuals = dy - x_mat @ coeffs
        sse = np.sum(residuals ** 2)
        mse = sse / (n_dy - len(coeffs))

        try:
            var_covar = mse * np.linalg.inv(x_mat.T @ x_mat)
            se_gamma = np.sqrt(var_covar[1, 1])
        except np.linalg.LinAlgError:
            return 0.0, 1.0

        if se_gamma <= 0:
            return 0.0, 1.0

        adf_stat = gamma / se_gamma

        # Approximate p-value using MacKinnon critical values (with constant)
        # Critical values at 1%, 5%, 10% for n=500: -3.44, -2.87, -2.57
        if adf_stat < -3.44:
            p_value = 0.005
        elif adf_stat < -2.87:
            p_value = 0.03
        elif adf_stat < -2.57:
            p_value = 0.07
        elif adf_stat < -1.94:
            p_value = 0.15
        else:
            p_value = 0.50 + min(0.49, max(0, adf_stat) * 0.1)

        return adf_stat, p_value

    @staticmethod
    def _half_life(spread: np.ndarray) -> float:
        """
        Estimate mean-reversion half-life using AR(1) model.
        Half-life = -ln(2) / ln(theta) where theta is AR(1) coefficient.
        """
        n = len(spread)
        if n < 10:
            return float("inf")

        y = spread[1:]
        x = spread[:-1]

        # OLS: y = alpha + theta * x
        x_mat = np.column_stack([np.ones(len(x)), x])
        try:
            coeffs = np.linalg.lstsq(x_mat, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return float("inf")

        theta = coeffs[1]

        if theta <= 0 or theta >= 1:
            return float("inf")

        half_life = -np.log(2) / np.log(theta)
        return max(1.0, half_life)

    def test_cointegration(
        self,
        prices_a: np.ndarray,
        prices_b: np.ndarray,
        significance: float = 0.05,
    ) -> CointegrationResult:
        """
        Test cointegration between two price series (Engle-Granger).

        Args:
            prices_a: Prices of asset A (e.g., Gold)
            prices_b: Prices of asset B (e.g., Bitcoin)
            significance: P-value threshold for cointegration

        Returns:
            CointegrationResult
        """
        if len(prices_a) != len(prices_b):
            raise ValueError("Price series must have equal length")

        if len(prices_a) < 30:
            return CointegrationResult(
                is_cointegrated=False,
                adf_statistic=0.0,
                p_value_approx=1.0,
                hedge_ratio=0.0,
                half_life=float("inf"),
                spread_mean=0.0,
                spread_std=0.0,
            )

        # Step 1: OLS regression to find hedge ratio
        _, hedge_ratio, residuals = self._ols_regression(prices_a, prices_b)

        # Step 2: ADF test on residuals
        adf_stat, p_value = self._adf_test(residuals)

        # Step 3: Compute spread statistics
        spread_mean = float(np.mean(residuals))
        spread_std = float(np.std(residuals))

        # Step 4: Half-life of mean reversion
        half_life = self._half_life(residuals)

        return CointegrationResult(
            is_cointegrated=p_value < significance,
            adf_statistic=float(adf_stat),
            p_value_approx=float(p_value),
            hedge_ratio=float(hedge_ratio),
            half_life=float(half_life),
            spread_mean=spread_mean,
            spread_std=spread_std,
        )

    @staticmethod
    def compute_spread(
        prices_a: np.ndarray,
        prices_b: np.ndarray,
        hedge_ratio: float,
    ) -> np.ndarray:
        """Compute the spread: A - hedge_ratio * B."""
        return prices_a - hedge_ratio * prices_b

    @staticmethod
    def compute_zscore(
        spread: np.ndarray,
        lookback: int = 50,
    ) -> np.ndarray:
        """
        Compute rolling z-score of the spread (vectorized).

        Args:
            spread: Spread series
            lookback: Rolling window for mean/std

        Returns:
            Z-score array (NaN for first lookback-1 elements)
        """
        n = len(spread)
        if n < lookback:
            return np.full(n, np.nan)

        # Vectorized rolling mean/std via cumsum trick
        cumsum = np.cumsum(spread)
        cumsum2 = np.cumsum(spread ** 2)

        # Prepend 0 for correct window sums
        cumsum = np.concatenate([[0.0], cumsum])
        cumsum2 = np.concatenate([[0.0], cumsum2])

        zscore = np.full(n, np.nan)
        for i in range(lookback - 1, n):
            s = cumsum[i + 1] - cumsum[i + 1 - lookback]
            s2 = cumsum2[i + 1] - cumsum2[i + 1 - lookback]
            mean = s / lookback
            var = s2 / lookback - mean * mean
            std = np.sqrt(max(0.0, var))
            if std > 0:
                zscore[i] = (spread[i] - mean) / std
            else:
                zscore[i] = 0.0

        return zscore

    @staticmethod
    def rolling_hedge_ratio(
        prices_a: np.ndarray,
        prices_b: np.ndarray,
        window: int = 504,
    ) -> np.ndarray:
        """
        Compute rolling hedge ratio over a window.

        Args:
            prices_a: Prices of asset A
            prices_b: Prices of asset B
            window: Rolling OLS window

        Returns:
            Array of rolling hedge ratios (NaN for first window-1 elements)
        """
        n = len(prices_a)
        ratios = np.full(n, np.nan)

        for i in range(window - 1, n):
            a_win = prices_a[i - window + 1: i + 1]
            b_win = prices_b[i - window + 1: i + 1]

            x_mat = np.column_stack([np.ones(window), b_win])
            try:
                coeffs = np.linalg.lstsq(x_mat, a_win, rcond=None)[0]
                ratios[i] = coeffs[1]
            except np.linalg.LinAlgError:
                ratios[i] = np.nan

        return ratios
