"""
Logging configuration using loguru.
Provides structured logging with rotation and retention.
"""

import sys
from pathlib import Path

from loguru import logger

from src.utils.config import get_settings


def setup_logger() -> None:
    """
    Configure loguru logger with file rotation and structured formatting.
    """
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Windows consoles default to a legacy code page (cp1252 on Italian
    # systems): any log message containing chars like the em-dash gets
    # encoded to bytes such as 0x97 on the stderr FD. Besides rendering
    # as garbage, those bytes poison pytest's FD-level capture tempfile
    # (read back as strict UTF-8 -> UnicodeDecodeError cascading over the
    # whole suite). Force UTF-8 on the stream loguru is about to capture.
    for _stream in (sys.stderr, sys.stdout):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except (ValueError, OSError):
                pass  # stream already closed/replaced (e.g. under capture)

    # Console handler with colored output
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File handler with rotation
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "algotrader_{time:YYYY-MM-DD}.log",
        level="DEBUG",  # Always log DEBUG to file
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | " "{name}:{function}:{line} | {message}"
        ),
        rotation="00:00",  # Rotate at midnight
        retention="30 days",  # Keep logs for 30 days
        compression="zip",  # Compress rotated logs
        backtrace=True,
        diagnose=True,
        enqueue=True,  # Async logging
    )

    # Separate error log file
    logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}\n{exception}"
        ),
        rotation="00:00",
        retention="90 days",  # Keep error logs longer
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    # JSON structured log file (for log aggregation / parsing)
    logger.add(
        log_dir / "mantis.json.log",
        level="INFO",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        serialize=True,  # Built-in JSON serialization (includes extra fields like request_id)
        enqueue=True,
    )

    logger.info(
        f"Logger initialized - Environment: {settings.environment}, "
        f"Log level: {settings.log_level}"
    )


def get_logger(name: str):
    """
    Get a logger instance with a specific name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logger.bind(name=name)
