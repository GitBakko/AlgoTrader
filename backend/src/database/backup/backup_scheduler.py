"""
Automated backup scheduler.
Schedules periodic database backups at configured times.
"""

import asyncio
from datetime import datetime

from croniter import croniter
from loguru import logger

from src.database.backup.backup_manager import BackupManager
from src.utils.config import get_settings


class BackupScheduler:
    """
    Scheduler for automated database backups.
    Runs backups according to cron schedule.
    """

    def __init__(self, backup_manager: BackupManager | None = None):
        """
        Initialize backup scheduler.

        Args:
            backup_manager: BackupManager instance (creates new if None)
        """
        self.settings = get_settings()
        self.backup_manager = backup_manager or BackupManager()
        self.cron_schedule = getattr(self.settings, "backup_schedule_cron", "0 2 * * *")
        self.enabled = getattr(self.settings, "backup_enabled", False)
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        """Start the backup scheduler."""
        if not self.enabled:
            logger.info("Backup scheduler disabled (BACKUP_ENABLED=false)")
            return

        if self._running:
            logger.warning("Backup scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info(f"Backup scheduler started: {self.cron_schedule}")

    def stop(self):
        """Stop the backup scheduler."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

        logger.info("Backup scheduler stopped")

    async def _run_scheduler(self):
        """Run the scheduler loop."""
        try:
            cron = croniter(self.cron_schedule, datetime.now())

            while self._running:
                # Get next scheduled time
                next_run = cron.get_next(datetime)
                now = datetime.now()
                sleep_seconds = (next_run - now).total_seconds()

                if sleep_seconds > 0:
                    logger.info(
                        f"Next backup scheduled at: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"({sleep_seconds / 3600:.1f}h from now)"
                    )

                    # Sleep until next run
                    try:
                        await asyncio.sleep(sleep_seconds)
                    except asyncio.CancelledError:
                        break

                # Run backup
                if self._running:
                    await self._run_backup()

        except Exception as e:
            logger.error(f"Backup scheduler error: {e}")
            self._running = False

    async def _run_backup(self):
        """Execute a scheduled backup."""
        try:
            logger.info("Running scheduled database backup...")

            result = await self.backup_manager.create_backup()

            if result.get("success"):
                logger.success(
                    f"Scheduled backup completed: {result['size_mb']} MB, "
                    f"{result['duration_seconds']}s"
                )

                # Send alert on success (if alerting enabled)
                try:
                    from src.monitoring.alerting.alert_manager import get_alert_manager
                    from src.monitoring.alerting.schemas import Alert, AlertSeverity, AlertType

                    alert_manager = get_alert_manager()
                    alert = Alert(
                        alert_type=AlertType.BACKUP_COMPLETE,  # Need to add this type
                        severity=AlertSeverity.INFO,
                        title="Database Backup Completed",
                        message=f"Backup successful: {result['backup_file']} ({result['size_mb']} MB)",
                        details=result,
                    )
                    await alert_manager.send_alert(alert)
                except Exception as e:
                    logger.warning(f"Failed to send backup alert: {e}")

            else:
                error = result.get("error", "Unknown error")
                logger.error(f"Scheduled backup failed: {error}")

                # Send alert on failure
                try:
                    from src.monitoring.alerting.alert_manager import get_alert_manager
                    from src.monitoring.alerting.schemas import Alert, AlertSeverity, AlertType

                    alert_manager = get_alert_manager()
                    alert = Alert(
                        alert_type=AlertType.DATABASE_FAILURE,
                        severity=AlertSeverity.CRITICAL,
                        title="Database Backup Failed",
                        message=f"Scheduled backup failed: {error}",
                        details=result,
                    )
                    await alert_manager.send_alert(alert)
                except Exception as e:
                    logger.warning(f"Failed to send backup failure alert: {e}")

        except Exception as e:
            logger.error(f"Backup execution failed: {e}")

    async def run_manual_backup(self) -> dict:
        """
        Run a manual backup immediately.

        Returns:
            Backup result dict
        """
        logger.info("Running manual database backup...")
        return await self.backup_manager.create_backup()
