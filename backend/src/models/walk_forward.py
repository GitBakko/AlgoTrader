"""
Walk-forward optimization splitter.
Implements expanding/rolling window splits with purge gap and embargo
to prevent data leakage in time-series cross-validation.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np


@dataclass
class WalkForwardSplit:
    """A single walk-forward split with train/val/test indices."""

    fold_index: int
    train_start: int
    train_end: int  # exclusive
    val_start: int
    val_end: int  # exclusive
    test_start: int
    test_end: int  # exclusive

    @property
    def train_indices(self) -> np.ndarray:
        return np.arange(self.train_start, self.train_end)

    @property
    def val_indices(self) -> np.ndarray:
        return np.arange(self.val_start, self.val_end)

    @property
    def test_indices(self) -> np.ndarray:
        return np.arange(self.test_start, self.test_end)


class WalkForwardSplitter:
    """
    Walk-forward cross-validation splitter with purge gap and embargo.

    Timeline for each fold:
    [TRAIN...][PURGE_GAP][VALIDATION][EMBARGO][TEST]

    The purge gap prevents leakage from overlapping prediction horizons.
    The embargo adds extra safety margin after validation.

    Parameters from docs/03-ML-STRATEGY.md:
    - train_window = 252 trading days
    - val_window = 63 trading days
    - test_window = 21 trading days
    - step_size = 21 trading days
    - purge_gap = 5 days
    - embargo = 2 days
    """

    def __init__(
        self,
        train_window: int = 252,
        val_window: int = 63,
        test_window: int = 21,
        step_size: int = 21,
        purge_gap: int = 5,
        embargo: int = 2,
    ):
        """
        Args:
            train_window: Number of bars for training
            val_window: Number of bars for validation
            test_window: Number of bars for testing
            step_size: Number of bars to advance between folds
            purge_gap: Gap between train and validation to prevent leakage
            embargo: Additional gap after validation before test
        """
        self.train_window = train_window
        self.val_window = val_window
        self.test_window = test_window
        self.step_size = step_size
        self.purge_gap = purge_gap
        self.embargo = embargo

    @property
    def min_samples(self) -> int:
        """Minimum number of samples needed for at least one fold."""
        return (
            self.train_window + self.purge_gap + self.val_window + self.embargo + self.test_window
        )

    def split(self, n_samples: int) -> Iterator[WalkForwardSplit]:
        """
        Generate walk-forward splits.

        Args:
            n_samples: Total number of samples in the dataset

        Yields:
            WalkForwardSplit objects with train/val/test index ranges
        """
        if n_samples < self.min_samples:
            raise ValueError(
                f"Need at least {self.min_samples} samples for one fold, "
                f"got {n_samples}. Reduce window sizes or get more data."
            )

        fold_index = 0
        train_start = 0

        while True:
            train_end = train_start + self.train_window
            val_start = train_end + self.purge_gap
            val_end = val_start + self.val_window
            test_start = val_end + self.embargo
            test_end = test_start + self.test_window

            # Stop if test set exceeds available data
            if test_end > n_samples:
                break

            yield WalkForwardSplit(
                fold_index=fold_index,
                train_start=train_start,
                train_end=train_end,
                val_start=val_start,
                val_end=val_end,
                test_start=test_start,
                test_end=test_end,
            )

            fold_index += 1
            train_start += self.step_size

    def get_n_splits(self, n_samples: int) -> int:
        """Count how many folds are possible with given data size."""
        return sum(1 for _ in self.split(n_samples))

    def describe(self, n_samples: int) -> dict:
        """
        Describe the walk-forward configuration.

        Returns:
            Dict with configuration and fold count info
        """
        n_splits = self.get_n_splits(n_samples) if n_samples >= self.min_samples else 0
        return {
            "train_window": self.train_window,
            "val_window": self.val_window,
            "test_window": self.test_window,
            "step_size": self.step_size,
            "purge_gap": self.purge_gap,
            "embargo": self.embargo,
            "min_samples": self.min_samples,
            "n_samples": n_samples,
            "n_splits": n_splits,
        }
