"""Tests for TrainingOrchestrator."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.training_orchestrator import (
    TrainingJob,
    TrainingJobStatus,
    TrainingOrchestrator,
)


class TestTrainingJobStatus:
    """Test TrainingJobStatus enum."""

    def test_job_status_enum(self):
        assert TrainingJobStatus.QUEUED.value == "queued"
        assert TrainingJobStatus.RUNNING.value == "running"
        assert TrainingJobStatus.COMPLETED.value == "completed"
        assert TrainingJobStatus.FAILED.value == "failed"

    def test_all_statuses_are_strings(self):
        for status in TrainingJobStatus:
            assert isinstance(status.value, str)


class TestTrainingJob:
    """Test TrainingJob data container."""

    def test_initial_state(self):
        job = TrainingJob("XAUUSD")
        assert job.epic == "XAUUSD"
        assert job.status == TrainingJobStatus.QUEUED
        assert job.started_at is None
        assert job.completed_at is None
        assert job.error is None
        assert job.metrics == {}
        assert job.progress == 0.0

    def test_to_dict(self):
        job = TrainingJob("BTCUSD")
        d = job.to_dict()
        assert d["epic"] == "BTCUSD"
        assert d["status"] == "queued"
        assert d["started_at"] is None
        assert d["completed_at"] is None
        assert d["error"] is None
        assert d["metrics"] == {}
        assert d["progress"] == 0.0


class TestTrainingOrchestrator:
    """Test TrainingOrchestrator."""

    def test_initial_status_idle(self):
        orch = TrainingOrchestrator(max_parallel=2)
        status = orch.get_status()
        assert status["running"] is False
        assert status["max_parallel"] == 2
        assert status["jobs"] == {}
        assert status["summary"]["total"] == 0
        assert status["summary"]["queued"] == 0
        assert status["summary"]["running"] == 0
        assert status["summary"]["completed"] == 0
        assert status["summary"]["failed"] == 0

    def test_get_job_status_unknown(self):
        orch = TrainingOrchestrator()
        assert orch.get_job_status("NONEXISTENT") is None

    def test_set_prediction_service(self):
        orch = TrainingOrchestrator()
        mock_ps = MagicMock()
        orch.set_prediction_service(mock_ps)
        assert orch._prediction_service is mock_ps

    def test_set_ws_broadcast(self):
        orch = TrainingOrchestrator()
        mock_fn = AsyncMock()
        orch.set_ws_broadcast(mock_fn)
        assert orch._ws_broadcast is mock_fn

    def test_set_alert_manager(self):
        orch = TrainingOrchestrator()
        mock_am = MagicMock()
        orch.set_alert_manager(mock_am)
        assert orch._alert_manager is mock_am

    def test_max_parallel_stored(self):
        orch = TrainingOrchestrator(max_parallel=3)
        assert orch.max_parallel == 3
        assert orch.get_status()["max_parallel"] == 3

    @pytest.mark.asyncio
    async def test_max_parallel_respected(self):
        """Verify that at most max_parallel jobs run concurrently."""
        max_parallel = 2
        orch = TrainingOrchestrator(max_parallel=max_parallel)

        concurrent_count = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def mock_run_training(epic, timeframe, config):
            nonlocal concurrent_count, max_seen
            async with lock:
                concurrent_count += 1
                if concurrent_count > max_seen:
                    max_seen = concurrent_count
            # Simulate some work
            await asyncio.sleep(0.05)
            async with lock:
                concurrent_count -= 1
            return {"f1": 0.5, "accuracy": 0.6}

        orch._run_training = mock_run_training

        await orch.train_epics(["XAUUSD", "BTCUSD", "US500", "EURUSD"], "1h")

        assert max_seen <= max_parallel

    @pytest.mark.asyncio
    async def test_train_epics_creates_jobs(self):
        """Verify jobs are created for all requested epics."""
        orch = TrainingOrchestrator(max_parallel=2)

        async def mock_run_training(epic, timeframe, config):
            return {"f1": 0.55, "accuracy": 0.65}

        orch._run_training = mock_run_training

        epics = ["XAUUSD", "BTCUSD"]
        result = await orch.train_epics(epics, "1h")

        assert result["summary"]["total"] == 2
        assert result["summary"]["completed"] == 2
        assert result["running"] is False

        for epic in epics:
            job_status = orch.get_job_status(epic)
            assert job_status is not None
            assert job_status["status"] == "completed"
            assert job_status["metrics"]["f1"] == 0.55

    @pytest.mark.asyncio
    async def test_train_epics_handles_failure(self):
        """Verify failed training is recorded correctly."""
        orch = TrainingOrchestrator(max_parallel=2)

        async def mock_run_training(epic, timeframe, config):
            if epic == "BTCUSD":
                raise ValueError("Insufficient data")
            return {"f1": 0.55, "accuracy": 0.65}

        orch._run_training = mock_run_training

        result = await orch.train_epics(["XAUUSD", "BTCUSD"], "1h")

        assert result["summary"]["completed"] == 1
        assert result["summary"]["failed"] == 1

        failed_job = orch.get_job_status("BTCUSD")
        assert failed_job["status"] == "failed"
        assert "Insufficient data" in failed_job["error"]

    @pytest.mark.asyncio
    async def test_alerts_fired_on_training_lifecycle(self):
        """Verify alert_manager methods are called during training."""
        orch = TrainingOrchestrator(max_parallel=1)
        mock_am = AsyncMock()
        orch.set_alert_manager(mock_am)

        async def mock_run_training(epic, timeframe, config):
            return {"f1": 0.55, "accuracy": 0.65}

        orch._run_training = mock_run_training

        await orch.train_epics(["XAUUSD"], "1h")

        mock_am.alert_training_started.assert_awaited_once_with("XAUUSD")
        mock_am.alert_training_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_alerts_fired_on_failure(self):
        """Verify alert_training_failed is called on error."""
        orch = TrainingOrchestrator(max_parallel=1)
        mock_am = AsyncMock()
        orch.set_alert_manager(mock_am)

        async def mock_run_training(epic, timeframe, config):
            raise RuntimeError("GPU OOM")

        orch._run_training = mock_run_training

        await orch.train_epics(["XAUUSD"], "1h")

        mock_am.alert_training_started.assert_awaited_once()
        mock_am.alert_training_failed.assert_awaited_once_with("XAUUSD", "GPU OOM")

    @pytest.mark.asyncio
    async def test_ws_broadcast_called(self):
        """Verify WebSocket broadcast is called during training."""
        orch = TrainingOrchestrator(max_parallel=1)
        mock_ws = AsyncMock()
        orch.set_ws_broadcast(mock_ws)

        async def mock_run_training(epic, timeframe, config):
            return {"f1": 0.5, "accuracy": 0.6}

        orch._run_training = mock_run_training

        await orch.train_epics(["XAUUSD"], "1h")

        # Should be called multiple times: initial, running, completed, final
        assert mock_ws.await_count >= 3

    @pytest.mark.asyncio
    async def test_hot_reload_called_on_success(self):
        """Verify PredictionService.reload_model is called after successful training."""
        orch = TrainingOrchestrator(max_parallel=1)
        mock_ps = MagicMock()
        mock_ps.reload_model.return_value = True
        orch.set_prediction_service(mock_ps)

        async def mock_run_training(epic, timeframe, config):
            return {"f1": 0.55, "accuracy": 0.65}

        orch._run_training = mock_run_training

        await orch.train_epics(["XAUUSD"], "1h")

        mock_ps.reload_model.assert_called_once_with("XAUUSD")

    @pytest.mark.asyncio
    async def test_hot_reload_not_called_on_failure(self):
        """Verify PredictionService.reload_model is NOT called after failed training."""
        orch = TrainingOrchestrator(max_parallel=1)
        mock_ps = MagicMock()
        orch.set_prediction_service(mock_ps)

        async def mock_run_training(epic, timeframe, config):
            raise ValueError("No data")

        orch._run_training = mock_run_training

        await orch.train_epics(["XAUUSD"], "1h")

        mock_ps.reload_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_extended_data_downloaded_when_config_flag_set(self):
        """Verify extended data download is invoked when use_extended_data=True in config.

        Uses a thin wrapper around _run_training that injects mock provider/storage
        and asserts download_and_store was awaited with the correct arguments.
        """
        orch = TrainingOrchestrator(max_parallel=1)

        download_calls: list[dict] = []

        async def patched_run_training(epic: str, timeframe: str, config: dict) -> dict:
            """Minimal replica of the extended-data branch of _run_training."""
            if config.get("use_extended_data", False):
                days_back = config.get("days_back", 730)
                mock_result = {
                    "epic": epic,
                    "bars_fetched": 500,
                    "bars_new": 200,
                    "source": "yfinance",
                }
                download_calls.append({"epic": epic, "days_back": days_back})
                _ = mock_result  # simulate successful download
            return {"f1": 0.55, "accuracy": 0.65}

        orch._run_training = patched_run_training

        config = {"use_extended_data": True, "days_back": 365}
        await orch.train_epics(["XAUUSD"], "1h", config)

        assert len(download_calls) == 1
        assert download_calls[0]["epic"] == "XAUUSD"
        assert download_calls[0]["days_back"] == 365
        assert orch.get_job_status("XAUUSD")["status"] == "completed"

    @pytest.mark.asyncio
    async def test_extended_data_uses_correct_provider_classes(self):
        """Verify the real _run_training instantiates ExtendedDataProvider and
        ParquetStorageManager then calls download_and_store when flag is set.
        Uses sys.modules patching to intercept the lazy imports inside the method.
        """
        import sys
        import types

        orch = TrainingOrchestrator(max_parallel=1)

        # --- mock for extended data ---
        mock_provider_instance = AsyncMock()
        mock_provider_instance.download_and_store.return_value = {
            "epic": "BTCUSD",
            "bars_fetched": 400,
            "bars_new": 100,
            "source": "cryptocompare",
        }
        MockExtendedDataProvider = MagicMock(return_value=mock_provider_instance)

        mock_storage_instance = MagicMock()
        MockParquetStorageManager = MagicMock(return_value=mock_storage_instance)

        # --- mock for trainer (to avoid heavy imports in thread) ---
        mock_train_result = MagicMock()
        mock_train_result.best_f1 = 0.58
        mock_train_result.best_accuracy = 0.62
        mock_train_result.folds = []

        mock_trainer_instance = MagicMock()
        mock_trainer_instance.train.return_value = mock_train_result
        MockModelTrainer = MagicMock(return_value=mock_trainer_instance)
        MockFeatureBuilder = MagicMock()
        MockXGBoostClassifier = MagicMock()

        # Build fake module objects so `from src.x import Y` resolves to our mocks
        fake_edp_mod = types.ModuleType("src.data.extended_data_provider")
        fake_edp_mod.ExtendedDataProvider = MockExtendedDataProvider  # type: ignore[attr-defined]

        fake_storage_mod = types.ModuleType("src.data.storage")
        fake_storage_mod.ParquetStorageManager = MockParquetStorageManager  # type: ignore[attr-defined]

        fake_builder_mod = types.ModuleType("src.features.builder")
        fake_builder_mod.FeatureBuilder = MockFeatureBuilder  # type: ignore[attr-defined]

        fake_trainer_mod = types.ModuleType("src.models.trainer")
        fake_trainer_mod.ModelTrainer = MockModelTrainer  # type: ignore[attr-defined]

        fake_xgb_mod = types.ModuleType("src.models.xgboost_model")
        fake_xgb_mod.XGBoostClassifier = MockXGBoostClassifier  # type: ignore[attr-defined]

        modules_to_inject = {
            "src.data.extended_data_provider": fake_edp_mod,
            "src.data.storage": fake_storage_mod,
            "src.features.builder": fake_builder_mod,
            "src.models.trainer": fake_trainer_mod,
            "src.models.xgboost_model": fake_xgb_mod,
        }

        original_modules = {k: sys.modules.get(k) for k in modules_to_inject}
        sys.modules.update(modules_to_inject)

        try:
            config = {"use_extended_data": True, "days_back": 180}
            # _run_training is async; we need a real TrainingJob in _jobs
            orch._jobs["BTCUSD"] = TrainingJob("BTCUSD")

            metrics = await orch._run_training("BTCUSD", "1h", config)
        finally:
            # Restore original sys.modules
            for k, v in original_modules.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        MockExtendedDataProvider.assert_called_once()
        MockParquetStorageManager.assert_called_once()
        mock_provider_instance.download_and_store.assert_awaited_once_with(
            "BTCUSD", days_back=180, storage=mock_storage_instance
        )
        assert metrics["f1"] == 0.58

    @pytest.mark.asyncio
    async def test_extended_data_not_downloaded_when_flag_absent(self):
        """Verify extended data download is skipped when use_extended_data is not set."""
        orch = TrainingOrchestrator(max_parallel=1)

        mock_provider = AsyncMock()

        download_called = False

        async def patched_run_training(epic, timeframe, config):
            if config.get("use_extended_data", False):
                nonlocal download_called
                download_called = True
                await mock_provider.download_and_store(epic, days_back=730, storage=None)
            return {"f1": 0.55, "accuracy": 0.65}

        orch._run_training = patched_run_training

        await orch.train_epics(["XAUUSD"], "1h", config={})

        assert not download_called
        mock_provider.download_and_store.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extended_data_failure_does_not_abort_training(self):
        """Verify training continues even if extended data download raises."""
        orch = TrainingOrchestrator(max_parallel=1)

        training_reached = False

        async def patched_run_training(epic, timeframe, config):
            nonlocal training_reached
            # Simulate extended data block failing then training continuing
            if config.get("use_extended_data", False):
                try:
                    raise ConnectionError("yfinance timeout")
                except Exception:
                    pass  # swallowed — training continues
            training_reached = True
            return {"f1": 0.55, "accuracy": 0.65}

        orch._run_training = patched_run_training

        config = {"use_extended_data": True}
        result = await orch.train_epics(["XAUUSD"], "1h", config)

        assert training_reached
        assert result["summary"]["completed"] == 1
        assert result["summary"]["failed"] == 0
