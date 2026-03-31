"""
Training orchestrator: manages parallel model training with status tracking,
hot-reload into PredictionService, and alert/WebSocket notifications.
"""

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from loguru import logger


class TrainingJobStatus(str, Enum):
    """Status of a training job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingJob:
    """State container for a single training job."""

    def __init__(self, epic: str):
        self.epic = epic
        self.status: TrainingJobStatus = TrainingJobStatus.QUEUED
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.error: str | None = None
        self.metrics: dict[str, Any] = {}
        self.progress: float = 0.0

    def to_dict(self) -> dict:
        return {
            "epic": self.epic,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metrics": self.metrics,
            "progress": self.progress,
        }


class TrainingOrchestrator:
    """
    Manages parallel model training with status tracking.

    Features:
    - Parallel training with configurable concurrency (semaphore)
    - Per-job status tracking (queued/running/completed/failed)
    - Auto hot-reload into PredictionService after training
    - Alert notifications (Telegram/InApp) on start/complete/fail
    - WebSocket broadcast of status updates
    """

    def __init__(self, max_parallel: int = 2):
        self.max_parallel = max_parallel
        self._executor = ThreadPoolExecutor(max_workers=max_parallel)
        self._jobs: dict[str, TrainingJob] = {}
        self._running = False
        self._prediction_service: Any | None = None
        self._ws_broadcast: Callable[..., Coroutine] | None = None
        self._alert_manager: Any | None = None

    def set_prediction_service(self, ps: Any) -> None:
        """Set the PredictionService instance for hot-reload after training."""
        self._prediction_service = ps

    def set_ws_broadcast(self, fn: Callable[..., Coroutine]) -> None:
        """Set the WebSocket broadcast function for status updates."""
        self._ws_broadcast = fn

    def set_alert_manager(self, am: Any) -> None:
        """Set the AlertManager instance for training notifications."""
        self._alert_manager = am

    def get_status(self) -> dict:
        """Get full orchestrator status."""
        completed = sum(1 for j in self._jobs.values() if j.status == TrainingJobStatus.COMPLETED)
        failed = sum(1 for j in self._jobs.values() if j.status == TrainingJobStatus.FAILED)
        return {
            "running": self._running,
            "max_parallel": self.max_parallel,
            "jobs": {epic: job.to_dict() for epic, job in self._jobs.items()},
            # Flat fields for frontend compatibility
            "completed_count": completed,
            "failed_count": failed,
            "queue": [e for e, j in self._jobs.items() if j.status == TrainingJobStatus.QUEUED],
            "summary": {
                "total": len(self._jobs),
                "queued": sum(
                    1 for j in self._jobs.values() if j.status == TrainingJobStatus.QUEUED
                ),
                "running": sum(
                    1 for j in self._jobs.values() if j.status == TrainingJobStatus.RUNNING
                ),
                "completed": completed,
                "failed": failed,
            },
        }

    def get_job_status(self, epic: str) -> dict | None:
        """Get status of a specific training job."""
        job = self._jobs.get(epic)
        return job.to_dict() if job else None

    async def train_epics(
        self,
        epics: list[str],
        timeframe: str = "1h",
        config: dict | None = None,
    ) -> dict:
        """
        Queue and process training for multiple epics in parallel.

        Args:
            epics: List of asset epics to train
            timeframe: Timeframe for training data
            config: Optional training configuration overrides

        Returns:
            Final orchestrator status dict
        """
        self._running = True
        config = config or {}
        semaphore = asyncio.Semaphore(self.max_parallel)

        # Create jobs for all epics
        for epic in epics:
            job = TrainingJob(epic)
            self._jobs[epic] = job

        await self._broadcast_status()

        # Launch all training tasks (semaphore limits concurrency)
        tasks = [self._train_one(epic, semaphore, timeframe, config) for epic in epics]
        await asyncio.gather(*tasks, return_exceptions=True)

        self._running = False
        await self._broadcast_status()
        return self.get_status()

    async def _train_one(
        self,
        epic: str,
        semaphore: asyncio.Semaphore,
        timeframe: str,
        config: dict,
    ) -> None:
        """Train a single epic, respecting the concurrency semaphore."""
        async with semaphore:
            job = self._jobs[epic]
            job.status = TrainingJobStatus.RUNNING
            job.started_at = datetime.now(UTC)
            job.progress = 0.1

            # Fire training started alert
            if self._alert_manager:
                try:
                    await self._alert_manager.alert_training_started(epic)
                except Exception as e:
                    logger.warning(f"Failed to send training started alert for {epic}: {e}")

            await self._broadcast_status()

            try:
                metrics = await self._run_training(epic, timeframe, config)

                # Success
                job.status = TrainingJobStatus.COMPLETED
                job.completed_at = datetime.now(UTC)
                job.metrics = metrics
                job.progress = "Complete"

                # Hot-reload model into PredictionService
                if self._prediction_service:
                    try:
                        reloaded = self._prediction_service.reload_model(epic)
                        if reloaded:
                            logger.info(f"Hot-reloaded model for {epic}")
                        else:
                            logger.warning(f"Hot-reload failed for {epic}")
                    except Exception as e:
                        logger.warning(f"Hot-reload error for {epic}: {e}")

                # Fire training complete alert
                duration_s = (
                    (job.completed_at - job.started_at).total_seconds() if job.started_at else 0.0
                )
                if self._alert_manager:
                    try:
                        await self._alert_manager.alert_training_complete(
                            epic=epic,
                            f1=metrics.get("f1_macro", 0.0),
                            accuracy=metrics.get("accuracy", 0.0),
                            duration_s=duration_s,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send training complete alert for {epic}: {e}")

                logger.info(
                    f"Training completed for {epic}: "
                    f"F1={metrics.get('f1_macro', 0):.4f}, "
                    f"Accuracy={metrics.get('accuracy', 0):.4f}, "
                    f"Duration={duration_s:.0f}s"
                )

            except Exception as e:
                job.status = TrainingJobStatus.FAILED
                job.completed_at = datetime.now(UTC)
                job.error = str(e)
                job.progress = 0.0
                logger.error(f"Training failed for {epic}: {e}")

                # Fire training failed alert
                if self._alert_manager:
                    try:
                        await self._alert_manager.alert_training_failed(epic, str(e))
                    except Exception as ae:
                        logger.warning(f"Failed to send training failed alert for {epic}: {ae}")

            await self._broadcast_status()

    async def _run_training(self, epic: str, timeframe: str, config: dict) -> dict:
        """
        Execute the actual training in a thread pool.

        Returns:
            Dict with training metrics (f1, accuracy, etc.)
        """
        # If config requests extended data, download before training
        if config.get("use_extended_data", False):
            days_back = config.get("days_back", 730)
            job = self._jobs.get(epic)
            if job:
                job.progress = "Downloading extended data..."
            await self._broadcast_status()

            from src.data.extended_data_provider import ExtendedDataProvider
            from src.data.storage import ParquetStorageManager

            provider = ExtendedDataProvider()
            storage = ParquetStorageManager()
            try:
                result = await provider.download_and_store(
                    epic, days_back=days_back, storage=storage
                )
                logger.info(
                    f"Extended data for {epic}: {result.get('bars_new', 0)} new bars"
                    f" from {result.get('source')}"
                )
            except Exception as e:
                logger.warning(
                    f"Extended data download failed for {epic}: {e}"
                    " — training with existing data"
                )

            job = self._jobs.get(epic)
            if job:
                job.progress = "Training..."
            await self._broadcast_status()

        from src.features.builder import FeatureBuilder
        from src.models.trainer import ModelTrainer
        from src.models.xgboost_model import XGBoostClassifier

        loop = asyncio.get_event_loop()

        def _do_train() -> dict:
            trainer = ModelTrainer(
                feature_builder=FeatureBuilder(),
            )
            model = XGBoostClassifier()

            result = trainer.train(
                model=model,
                epic=epic,
                timeframe=timeframe,
                save_best=True,
                multi_timeframe=config.get("multi_timeframe", False),
                include_sentiment=config.get("include_sentiment", False),
            )

            # Extract metrics from TrainingResult
            avg_test = result.avg_test_metrics or {}
            avg_val = result.avg_val_metrics or {}
            metrics: dict[str, Any] = {
                "f1_macro": avg_test.get("f1_macro", avg_val.get("f1_macro", 0.0)),
                "accuracy": avg_test.get("accuracy", avg_val.get("accuracy", 0.0)),
                "num_folds": result.num_folds,
                "num_features": result.num_features,
                "duration_seconds": result.training_duration_seconds,
            }

            return metrics

        return await loop.run_in_executor(self._executor, _do_train)

    async def _broadcast_status(self) -> None:
        """Broadcast current orchestrator status via WebSocket."""
        if self._ws_broadcast:
            try:
                status = self.get_status()
                await self._ws_broadcast({"type": "training_status", "data": status})
            except Exception as e:
                logger.debug(f"WebSocket broadcast failed: {e}")
