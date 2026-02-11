"""Tests for walk-forward splitter module."""

import pytest

from src.models.walk_forward import WalkForwardSplitter


class TestWalkForwardSplitter:
    def test_min_samples(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            purge_gap=5, embargo=2
        )
        assert splitter.min_samples == 100 + 5 + 30 + 2 + 10  # 147

    def test_insufficient_data_raises(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            purge_gap=5, embargo=2
        )
        with pytest.raises(ValueError, match="Need at least"):
            list(splitter.split(50))

    def test_single_fold(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            step_size=10, purge_gap=5, embargo=2
        )
        splits = list(splitter.split(147))
        assert len(splits) == 1

    def test_multiple_folds(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            step_size=10, purge_gap=5, embargo=2
        )
        # 147 + 10 = 157 should give 2 folds
        splits = list(splitter.split(157))
        assert len(splits) == 2

    def test_fold_indices_are_valid(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            step_size=10, purge_gap=5, embargo=2
        )
        n = 300
        for split in splitter.split(n):
            # All indices within bounds
            assert split.train_start >= 0
            assert split.test_end <= n

            # Correct sizes
            assert len(split.train_indices) == 100
            assert len(split.val_indices) == 30
            assert len(split.test_indices) == 10

            # No overlap between sets
            train_set = set(split.train_indices.tolist())
            val_set = set(split.val_indices.tolist())
            test_set = set(split.test_indices.tolist())
            assert len(train_set & val_set) == 0
            assert len(train_set & test_set) == 0
            assert len(val_set & test_set) == 0

    def test_purge_gap_exists(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            step_size=10, purge_gap=5, embargo=2
        )
        splits = list(splitter.split(200))
        for split in splits:
            # Gap between train_end and val_start should be purge_gap
            assert split.val_start - split.train_end == 5

    def test_embargo_exists(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            step_size=10, purge_gap=5, embargo=2
        )
        splits = list(splitter.split(200))
        for split in splits:
            # Gap between val_end and test_start should be embargo
            assert split.test_start - split.val_end == 2

    def test_folds_advance_by_step_size(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            step_size=20, purge_gap=5, embargo=2
        )
        splits = list(splitter.split(500))
        for i in range(1, len(splits)):
            assert splits[i].train_start - splits[i - 1].train_start == 20

    def test_get_n_splits(self):
        splitter = WalkForwardSplitter(
            train_window=100, val_window=30, test_window=10,
            step_size=10, purge_gap=5, embargo=2
        )
        n = splitter.get_n_splits(300)
        splits = list(splitter.split(300))
        assert n == len(splits)

    def test_describe(self):
        splitter = WalkForwardSplitter()
        desc = splitter.describe(500)
        assert "train_window" in desc
        assert "n_splits" in desc
        assert desc["n_samples"] == 500

    def test_default_params_match_docs(self):
        """Default params should match docs/03-ML-STRATEGY.md."""
        splitter = WalkForwardSplitter()
        assert splitter.train_window == 252
        assert splitter.val_window == 63
        assert splitter.test_window == 21
        assert splitter.step_size == 21
        assert splitter.purge_gap == 5
        assert splitter.embargo == 2
