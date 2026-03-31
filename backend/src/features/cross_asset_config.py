"""
Cross-asset feature configuration.
Defines correlation windows, lead-lag settings, and sector momentum parameters.
"""

# Rolling correlation window (in bars of the primary timeframe)
CORRELATION_WINDOW_SHORT = 20  # ~1 day of 1h bars — captures fast regime shifts
CORRELATION_WINDOW_LONG = 100  # ~4 days — captures structural correlation

# Lead-lag return windows: how many bars back to look for cross-asset returns
LEAD_LAG_WINDOWS = [1, 3, 6]  # 1h, 3h, 6h lead signals

# Sector momentum: simple average of returns within the cluster
SECTOR_MOMENTUM_WINDOW = 12  # 12h rolling average of cluster returns

# Correlation regime thresholds
CORR_REGIME_PANIC_THRESHOLD = 0.75  # Mean cross-asset correlation > 0.75 = panic
CORR_REGIME_NORMAL_RANGE = (0.20, 0.55)  # Normal correlation range
