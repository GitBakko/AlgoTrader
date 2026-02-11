"""
Unit tests for Parquet storage manager and DuckDB interface.
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from src.data.models import DataSource, OHLCBar
from src.data.storage import DuckDBInterface, OHLC_SCHEMA, ParquetStorageManager


def generate_test_candles(
    epic: str = "XAUUSD",
    timeframe: str = "1h",
    num_candles: int = 100,
    start_date: datetime | None = None,
) -> list[OHLCBar]:
    """Generate test OHLC candles."""
    if start_date is None:
        start_date = datetime(2024, 1, 1)

    candles = []
    current_time = start_date
    base_price = 2000.0

    for i in range(num_candles):
        # Simulate price movement
        price = base_price + (i % 50) * 0.5
        candle = OHLCBar(
            timestamp=current_time,
            open=price,
            high=price + 2.0,
            low=price - 1.5,
            close=price + 0.5,
            volume=1000 + (i * 10),
            epic=epic,
            timeframe=timeframe,
            source=DataSource.HISTORICAL,
        )
        candles.append(candle)
        current_time += timedelta(hours=1)

    return candles


@pytest.fixture
def test_data_dir(tmp_path):
    """Temporary data directory for testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    yield str(data_dir)
    # Cleanup handled automatically by tmp_path


@pytest.fixture
def storage_manager(test_data_dir):
    """ParquetStorageManager instance with test directory."""
    return ParquetStorageManager(data_dir=test_data_dir, compression="snappy")


@pytest.mark.unit
@pytest.mark.data
class TestParquetStorageManager:
    """Test ParquetStorageManager class."""

    def test_initialization(self, storage_manager, test_data_dir):
        """Test ParquetStorageManager initialization."""
        assert storage_manager.data_dir == test_data_dir
        assert storage_manager.compression == "snappy"

    def test_write_candles_creates_file(self, storage_manager, test_data_dir):
        """Test writing candles creates Parquet file."""
        candles = generate_test_candles(num_candles=100)
        written = storage_manager.write_candles(candles, epic="XAUUSD", timeframe="1h")

        assert written == 100
        # Verify file created
        parquet_files = list(Path(test_data_dir).rglob("*.parquet"))
        assert len(parquet_files) > 0

    def test_write_candles_empty_list(self, storage_manager):
        """Test writing empty candle list."""
        written = storage_manager.write_candles([], epic="XAUUSD", timeframe="1h")
        assert written == 0

    def test_write_candles_multiple_months(self, storage_manager, test_data_dir):
        """Test writing candles spanning multiple months creates multiple files."""
        # Generate candles for 3 months
        candles = generate_test_candles(
            num_candles=2000,  # ~83 days worth of hourly data
            start_date=datetime(2024, 1, 1),
        )
        written = storage_manager.write_candles(candles, epic="XAUUSD", timeframe="1h")

        assert written == 2000
        # Should create multiple monthly files
        parquet_files = list(Path(test_data_dir).rglob("*.parquet"))
        assert len(parquet_files) >= 2  # At least 2 months

    def test_read_candles(self, storage_manager):
        """Test reading candles from Parquet files."""
        # Write test data
        candles = generate_test_candles(num_candles=100)
        storage_manager.write_candles(candles, epic="XAUUSD", timeframe="1h")

        # Read back
        df = storage_manager.read_candles(epic="XAUUSD", timeframe="1h")

        assert len(df) == 100
        assert "timestamp" in df.columns
        assert "open" in df.columns
        assert "close" in df.columns

    def test_read_candles_with_date_filter(self, storage_manager):
        """Test reading candles with date filtering."""
        # Write test data
        start_date = datetime(2024, 1, 1)
        candles = generate_test_candles(num_candles=100, start_date=start_date)
        storage_manager.write_candles(candles, epic="XAUUSD", timeframe="1h")

        # Read with date filter
        filter_start = datetime(2024, 1, 2)
        filter_end = datetime(2024, 1, 3)
        df = storage_manager.read_candles(
            epic="XAUUSD",
            timeframe="1h",
            start_date=filter_start,
            end_date=filter_end,
        )

        # Should only get candles in range
        assert len(df) < 100
        assert all(df["timestamp"] >= filter_start)
        assert all(df["timestamp"] <= filter_end)

    def test_read_candles_nonexistent(self, storage_manager):
        """Test reading from nonexistent epic/timeframe returns empty DataFrame."""
        df = storage_manager.read_candles(epic="INVALID", timeframe="1h")

        assert len(df) == 0
        # Should still have correct schema
        assert "timestamp" in df.columns

    def test_append_candles_new_file(self, storage_manager):
        """Test appending candles to nonexistent file creates new file."""
        candles = generate_test_candles(num_candles=50)
        added = storage_manager.append_candles(candles, epic="BTCUSD", timeframe="1h")

        assert added == 50

    def test_append_candles_with_duplicates(self, storage_manager):
        """Test appending candles with duplicates removes duplicates."""
        # Write initial data
        candles = generate_test_candles(num_candles=100, start_date=datetime(2024, 1, 1))
        storage_manager.write_candles(candles, epic="XAUUSD", timeframe="1h")

        # Append with overlapping timestamps (last 20 duplicates)
        new_candles = generate_test_candles(
            num_candles=50,
            start_date=datetime(2024, 1, 1) + timedelta(hours=80),  # Start at hour 80
        )
        added = storage_manager.append_candles(new_candles, epic="XAUUSD", timeframe="1h")

        # Should only add 30 new candles (50 - 20 duplicates)
        assert added == 30

        # Total should be 130
        df = storage_manager.read_candles(epic="XAUUSD", timeframe="1h")
        assert len(df) == 130

    def test_append_candles_empty_list(self, storage_manager):
        """Test appending empty candle list."""
        added = storage_manager.append_candles([], epic="XAUUSD", timeframe="1h")
        assert added == 0

    def test_list_available_data(self, storage_manager):
        """Test listing available data."""
        # Write data for multiple assets/timeframes
        candles1 = generate_test_candles(epic="XAUUSD", timeframe="1h", num_candles=50)
        candles2 = generate_test_candles(epic="XAUUSD", timeframe="1d", num_candles=30)
        candles3 = generate_test_candles(epic="BTCUSD", timeframe="1h", num_candles=40)

        storage_manager.write_candles(candles1, epic="XAUUSD", timeframe="1h")
        storage_manager.write_candles(candles2, epic="XAUUSD", timeframe="1d")
        storage_manager.write_candles(candles3, epic="BTCUSD", timeframe="1h")

        # List available data
        available = storage_manager.list_available_data()

        assert "XAUUSD" in available
        assert "BTCUSD" in available
        assert "1h" in available["XAUUSD"]
        assert "1d" in available["XAUUSD"]
        assert "1h" in available["BTCUSD"]

    def test_get_metadata(self, storage_manager, test_data_dir):
        """Test getting Parquet file metadata."""
        candles = generate_test_candles(num_candles=100)
        storage_manager.write_candles(candles, epic="XAUUSD", timeframe="1h")

        # Get file path
        parquet_files = list(Path(test_data_dir).rglob("*.parquet"))
        assert len(parquet_files) > 0

        # Get metadata
        metadata = storage_manager.get_metadata(parquet_files[0])

        assert metadata.epic == "XAUUSD"
        assert metadata.timeframe == "1h"
        assert metadata.num_rows == 100
        assert metadata.file_size_bytes > 0
        assert metadata.compression == "SNAPPY"
        assert metadata.min_timestamp is not None
        assert metadata.max_timestamp is not None

    def test_get_storage_stats(self, storage_manager):
        """Test getting storage statistics."""
        # Write data for multiple assets
        candles1 = generate_test_candles(epic="XAUUSD", timeframe="1h", num_candles=100)
        candles2 = generate_test_candles(epic="BTCUSD", timeframe="1h", num_candles=50)

        storage_manager.write_candles(candles1, epic="XAUUSD", timeframe="1h")
        storage_manager.write_candles(candles2, epic="BTCUSD", timeframe="1h")

        # Get stats
        stats = storage_manager.get_storage_stats()

        assert stats.total_assets == 2
        assert stats.total_timeframes == 2
        assert stats.total_candles == 150
        assert stats.total_files >= 2
        assert stats.total_size_bytes > 0
        assert stats.earliest_data is not None
        assert stats.latest_data is not None


@pytest.mark.unit
@pytest.mark.data
class TestDuckDBInterface:
    """Test DuckDBInterface class."""

    @pytest.fixture
    def duckdb_interface(self, tmp_path, test_data_dir):
        """DuckDBInterface instance with test database."""
        db_path = str(tmp_path / "test.db")
        interface = DuckDBInterface(duckdb_path=db_path, data_dir=test_data_dir)
        yield interface
        interface.close()

    @pytest.fixture
    def populated_storage(self, test_data_dir):
        """Storage manager with test data."""
        storage = ParquetStorageManager(data_dir=test_data_dir)
        candles = generate_test_candles(epic="XAUUSD", timeframe="1h", num_candles=100)
        storage.write_candles(candles, epic="XAUUSD", timeframe="1h")
        return storage

    def test_connect(self, duckdb_interface):
        """Test DuckDB connection."""
        conn = duckdb_interface.connect()
        assert conn is not None

    def test_create_views(self, duckdb_interface, populated_storage):
        """Test creating DuckDB views."""
        duckdb_interface.create_views()

        # Verify views exist by querying them
        result = duckdb_interface.execute_query("SELECT COUNT(*) as count FROM ohlc_all")
        assert result is not None
        assert "count" in result.columns

    def test_execute_query_count(self, duckdb_interface, populated_storage):
        """Test executing query to count records."""
        duckdb_interface.create_views()

        result = duckdb_interface.execute_query("SELECT COUNT(*) as count FROM ohlc_all")
        assert len(result) == 1
        assert result["count"][0] == 100

    def test_execute_query_filter_by_epic(self, duckdb_interface, test_data_dir):
        """Test querying by epic."""
        # Create data for multiple epics
        storage = ParquetStorageManager(data_dir=test_data_dir)
        candles1 = generate_test_candles(epic="XAUUSD", timeframe="1h", num_candles=50)
        candles2 = generate_test_candles(epic="BTCUSD", timeframe="1h", num_candles=30)
        storage.write_candles(candles1, epic="XAUUSD", timeframe="1h")
        storage.write_candles(candles2, epic="BTCUSD", timeframe="1h")

        duckdb_interface.create_views()

        # Query XAUUSD only
        result = duckdb_interface.execute_query(
            "SELECT COUNT(*) as count FROM ohlc_all WHERE epic = 'XAUUSD'"
        )
        assert result["count"][0] == 50

        # Query using per-asset view
        result = duckdb_interface.execute_query("SELECT COUNT(*) as count FROM ohlc_xauusd")
        assert result["count"][0] == 50

    def test_execute_query_latest_view(self, duckdb_interface, populated_storage):
        """Test querying latest timestamps view."""
        duckdb_interface.create_views()

        result = duckdb_interface.execute_query(
            "SELECT epic, timeframe, total_candles FROM ohlc_latest"
        )
        assert len(result) == 1
        assert result["epic"][0] == "XAUUSD"
        assert result["timeframe"][0] == "1h"
        assert result["total_candles"][0] == 100

    def test_execute_query_aggregation(self, duckdb_interface, populated_storage):
        """Test query with aggregation."""
        duckdb_interface.create_views()

        result = duckdb_interface.execute_query("""
            SELECT
                MAX(high) as max_high,
                MIN(low) as min_low,
                AVG(close) as avg_close
            FROM ohlc_all
        """)
        assert len(result) == 1
        assert result["max_high"][0] > 0
        assert result["min_low"][0] > 0
        assert result["avg_close"][0] > 0

    def test_close_connection(self, duckdb_interface):
        """Test closing DuckDB connection."""
        duckdb_interface.connect()
        duckdb_interface.close()

        assert duckdb_interface._conn is None
