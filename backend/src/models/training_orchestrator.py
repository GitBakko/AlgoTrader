"""
Training orchestrator: manages parallel model training with status tracking,
hot-reload into PredictionService, and alert/WebSocket notifications.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Coroutine

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
        return {
            "running": self._running,
            "max_parallel": self.max_parallel,
            "jobs": {epic: job.to_dict() for epic, job in self._jobs.items()},
            "summary": {
                "total": len(self._jobs),
                "queued": sum(
                    1 for j in self._jobs.values()
                    if j.status == TrainingJobStatus.QUEUED
                ),
                "running": sum(
                    1 for j in self._jobs.values()
                    if j.status == TrainingJobStatus.RUNNING
                ),
                "completed": sum(
                    1 for j in self._jobs.values()
                    if j.status == TrainingJobStatus.COMPLETED
                ),
                "failed": sum(
                    1 for j in self._jobs.values()
                    if j.status == TrainingJobStatus.FAILED
                ),
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
        tasks = [
            self._train_one(epic, semaphore, timeframe, config)
            for epic in epics
        ]
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
                job.progress = 1.0

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
                    (job.completed_at - job.started_at).total_seconds()
                    if job.started_at
                    else 0.0
                )
                if self._alert_manager:
                    try:
                        await self._alert_manager.alert_training_complete(
                            epic=epic,
                            f1=metrics.get("f1", 0.0),
                            accuracy=metrics.get("accuracy", 0.0),
                            duration_s=duration_s,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to send training complete alert for {epic}: {e}"
                        )

                logger.info(
                    f"Training completed for {epic}: "
                    f"F1={metrics.get('f1', 0):.4f}, "
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
                        logger.warning(
                            f"Failed to send training failed alert for {epic}: {ae}"
                        )

            await self._broadcast_status()

    async def _run_training(
        self, epic: str, timeframe: str, config: dict
    ) -> dict:
        """
        Execute the actual training in a thread pool.

        Returns:
            Dict with training metrics (f1, accuracy, etc.)
        """
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
            metrics: dict[str, Any] = {
                "f1": result.best_f1 if hasattr(result, "best_f1") else 0.0,
                "accuracy": (
                    result.best_accuracy if hasattr(result, "best_accuracy") else 0.0
                ),
                "num_folds": len(result.folds) if hasattr(result, "folds") else 0,
            }

            # Use fold averages if best_* not available
            if hasattr(result, "folds") and result.folds:
                fold_f1s = [
                    f.test_metrics.get("f1_weighted", 0.0)
                    for f in result.folds
                    if hasattr(f, "test_metrics")
                ]
                fold_accs = [
                    f.test_metrics.get("accuracy", 0.0)
                    for f in result.folds
                    if hasattr(f, "test_metrics")
                ]
                if fold_f1s and metrics["f1"] == 0.0:
                    metrics["f1"] = sum(fold_f1s) / len(fold_f1s)
                if fold_accs and metrics["accuracy"] == 0.0:
                    metrics["accuracy"] = sum(fold_accs) / len(fold_accs)

            return metrics

        return await loop.run_in_executor(self._executor, _do_train)

    async def _broadcast_status(self) -> None:
        """Broadcast current orchestrator status via WebSocket."""
        if self._ws_broadcast:
            try:
                status = self.get_status()
                await self._ws_broadcast(
                    {"type": "training_status", "data": status}
                )
            except Exception as e:
                logger.debug(f"WebSocket broadcast failed: {e}")
