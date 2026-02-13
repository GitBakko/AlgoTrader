"""Tests for data models — coverage for computed properties."""

from datetime import datetime, timezone

from src.data.models import DataStorageStats, DownloadProgress, ParquetMetadata


class TestDownloadProgress:
    def test_progress_percentage(self):
        p = DownloadProgress(
            epic="GOLD", timeframe="HOUR", total_days=10, downloaded_days=5,
            total_candles=100, downloaded_candles=50,
            start_time=datetime.now(timezone.utc),
        )
        assert p.progress_percentage == 50.0

    def test_progress_percentage_zero_total(self):
        p = DownloadProgress(
            epic="GOLD", timeframe="HOUR", total_days=0, downloaded_days=0,
            total_candles=0, downloaded_candles=0,
            start_time=datetime.now(timezone.utc),
        )
        assert p.progress_percentage == 0.0

    def test_candles_per_second(self):
        p = DownloadProgress(
            epic="GOLD", timeframe="HOUR", total_days=1, downloaded_days=1,
            total_candles=100, downloaded_candles=100,
            start_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        assert p.candles_per_second > 0


class TestParquetMetadata:
    def test_file_size_mb(self):
        m = ParquetMetadata(
            epic="GOLD", timeframe="HOUR", file_path="/data/f.parquet",
            month="2024-01", num_rows=1000, file_size_bytes=1048576,
            compression="snappy", created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
            min_timestamp=datetime.now(timezone.utc),
            max_timestamp=datetime.now(timezone.utc),
        )
        assert m.file_size_mb == 1.0


class TestDataStorageStats:
    def test_total_size_mb_and_gb(self):
        s = DataStorageStats(
            total_assets=3, total_timeframes=3, total_candles=50000,
            total_files=9, total_size_bytes=1073741824,  # 1 GB
        )
        assert s.total_size_mb == 1024.0
        assert s.total_size_gb == 1.0
