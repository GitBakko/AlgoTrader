"""
Database backup manager using pg_dump.
Handles backup creation, compression, and retention.
"""

import asyncio
import gzip
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from src.utils.config import get_settings


class BackupManager:
    """
    Manager for PostgreSQL database backups.
    Creates compressed backups using pg_dump with automatic retention.
    """

    def __init__(self, backup_dir: str | None = None, retention_days: int | None = None):
        """
        Initialize backup manager.

        Args:
            backup_dir: Directory for storing backups (defaults to config)
            retention_days: Number of days to retain backups (defaults to config)
        """
        settings = get_settings()
        self.backup_dir = Path(backup_dir or getattr(settings, "backup_dir", "data/backups"))
        self.retention_days = retention_days or getattr(settings, "backup_retention_days", 30)

        # Database connection details
        self.db_host = settings.postgres_host
        self.db_port = settings.postgres_port
        self.db_name = settings.postgres_db
        self.db_user = settings.postgres_user
        self.db_password = settings.postgres_password

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Backup manager initialized: dir={self.backup_dir}, retention={self.retention_days}d"
        )

    async def create_backup(self, backup_name: str | None = None) -> dict[str, Any]:
        """
        Create a full database backup using pg_dump.

        Args:
            backup_name: Custom backup name (auto-generated if None)

        Returns:
            Dict with backup info: {
                'success': bool,
                'backup_file': str,
                'size_bytes': int,
                'duration_seconds': float,
                'timestamp': str
            }

        Raises:
            Exception: If backup fails
        """
        start_time = datetime.now(UTC)

        # Generate backup filename
        if backup_name is None:
            timestamp = start_time.strftime("%Y-%m-%d_%H%M%S")
            backup_name = f"mantis_backup_{timestamp}.sql.gz"

        backup_path = self.backup_dir / backup_name
        temp_sql_path = self.backup_dir / f"{backup_name}.tmp"

        try:
            logger.info(f"Starting database backup: {backup_name}")

            # Build pg_dump command
            pg_dump_cmd = [
                "pg_dump",
                "-h",
                self.db_host,
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                self.db_name,
                "-F",
                "p",  # Plain text format
                "-f",
                str(temp_sql_path),
                "--no-owner",  # Don't dump ownership commands
                "--no-acl",  # Don't dump access privileges
                "--verbose",
            ]

            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_password

            # Run pg_dump
            process = await asyncio.create_subprocess_exec(
                *pg_dump_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise Exception(f"pg_dump failed: {error_msg}")

            # Compress the SQL file with gzip
            logger.info(f"Compressing backup: {backup_name}")
            with open(temp_sql_path, "rb") as f_in:
                with gzip.open(backup_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove temporary uncompressed file
            temp_sql_path.unlink()

            # Get backup file size
            size_bytes = backup_path.stat().st_size

            # Calculate duration
            end_time = datetime.now(UTC)
            duration = (end_time - start_time).total_seconds()

            result = {
                "success": True,
                "backup_file": str(backup_path),
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "duration_seconds": round(duration, 2),
                "timestamp": start_time.isoformat(),
            }

            logger.success(
                f"Backup completed: {backup_name} ({result['size_mb']} MB, {duration:.1f}s)"
            )

            # Clean up old backups
            await self.cleanup_old_backups()

            return result

        except Exception as e:
            logger.error(f"Backup failed: {e}")

            # Cleanup temp files on error
            if temp_sql_path.exists():
                temp_sql_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

            return {
                "success": False,
                "error": str(e),
                "timestamp": start_time.isoformat(),
            }

    async def cleanup_old_backups(self) -> int:
        """
        Remove backups older than retention period.

        Returns:
            Number of backups deleted
        """
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=self.retention_days)
            deleted_count = 0

            for backup_file in self.backup_dir.glob("mantis_backup_*.sql.gz"):
                # Get file modification time
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

                if mtime < cutoff_date:
                    backup_file.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old backup: {backup_file.name}")

            if deleted_count > 0:
                logger.info(
                    f"Cleaned up {deleted_count} old backups (retention: {self.retention_days}d)"
                )

            return deleted_count

        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
            return 0

    async def list_backups(self) -> list[dict[str, Any]]:
        """
        List all available backups.

        Returns:
            List of backup info dicts with name, size, timestamp
        """
        backups = []

        try:
            for backup_file in sorted(self.backup_dir.glob("mantis_backup_*.sql.gz"), reverse=True):
                stat = backup_file.stat()
                backups.append(
                    {
                        "name": backup_file.name,
                        "path": str(backup_file),
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "age_days": (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days,
                    }
                )

        except Exception as e:
            logger.error(f"Failed to list backups: {e}")

        return backups

    async def restore_backup(self, backup_file: str) -> bool:
        """
        Restore database from a backup file.

        Args:
            backup_file: Path to backup file (.sql.gz)

        Returns:
            True if restore successful, False otherwise

        Warning:
            This will DROP and recreate the database. Use with caution!
        """
        backup_path = Path(backup_file)

        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_file}")
            return False

        try:
            logger.warning(f"Starting database restore from: {backup_path.name}")

            # Decompress backup
            temp_sql_path = self.backup_dir / f"{backup_path.stem}.tmp"
            with gzip.open(backup_path, "rb") as f_in:
                with open(temp_sql_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Build psql command
            psql_cmd = [
                "psql",
                "-h",
                self.db_host,
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                self.db_name,
                "-f",
                str(temp_sql_path),
                "--quiet",
            ]

            # Set PGPASSWORD
            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_password

            # Run psql
            process = await asyncio.create_subprocess_exec(
                *psql_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await process.communicate()

            # Cleanup temp file
            temp_sql_path.unlink()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Database restore failed: {error_msg}")
                return False

            logger.success(f"Database restored successfully from: {backup_path.name}")
            return True

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False
