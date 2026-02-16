"""
Database backup and recovery system.
Automated backups, WAL archiving, and point-in-time recovery.
"""

from src.database.backup.backup_manager import BackupManager

__all__ = ["BackupManager"]
