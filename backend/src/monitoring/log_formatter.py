"""
JSON log formatter for structured logging.
Formats logs as JSON for easy parsing and aggregation.
"""

import json
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from loguru import logger


def json_formatter(record: dict[str, Any]) -> str:
    """
    Format log record as JSON string.

    Args:
        record: Loguru record dict

    Returns:
        JSON-formatted log string

    Format:
        {
            "timestamp": "2026-02-16T10:30:00.123456Z",
            "level": "INFO",
            "logger": "src.trading.paper_loop",
            "message": "Trade executed",
            "extra": {...},
            "exception": {...}  # Only if exception present
        }
    """
    # Build base log dict
    log_dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "message": record["message"],
        "function": record["function"],
        "line": record["line"],
    }

    # Add extra fields if present
    if record.get("extra"):
        extra = {}
        for key, value in record["extra"].items():
            # Skip internal loguru fields
            if not key.startswith("_"):
                try:
                    # Ensure value is JSON-serializable
                    json.dumps({key: value})
                    extra[key] = value
                except (TypeError, ValueError):
                    extra[key] = str(value)

        if extra:
            log_dict["extra"] = extra

    # Add exception info if present
    if record.get("exception"):
        exc_type, exc_value, exc_traceback = record["exception"]
        log_dict["exception"] = {
            "type": exc_type.__name__ if exc_type else None,
            "value": str(exc_value) if exc_value else None,
            "traceback": (
                "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                if exc_traceback
                else None
            ),
        }

    # Convert to JSON string
    return json.dumps(log_dict, default=str)


def configure_json_logging(log_file: str = "logs/mantis.json.log", rotation: str = "100 MB"):
    """
    Configure Loguru to use JSON formatting.

    Args:
        log_file: Path to JSON log file
        rotation: Log rotation policy (e.g., "100 MB", "1 day")

    Example:
        configure_json_logging("logs/mantis.json.log", "1 day")
    """
    # Remove default handler
    logger.remove()

    # Add console handler with colored output (not JSON)
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    # Add JSON file handler
    logger.add(
        log_file,
        format=json_formatter,
        level="DEBUG",
        rotation=rotation,
        retention="30 days",
        compression="zip",
        serialize=False,  # We handle JSON formatting manually
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"JSON logging configured: {log_file}")


def add_context(**kwargs):
    """
    Add context fields to all subsequent log messages.

    Args:
        **kwargs: Context key-value pairs

    Example:
        with logger.contextualize(user_id=123, request_id="abc"):
            logger.info("Processing request")
    """
    return logger.contextualize(**kwargs)


# Pre-configured logger with common context
def get_trading_logger(epic: str):
    """
    Get logger with trading context.

    Args:
        epic: Asset epic

    Returns:
        Logger with epic context

    Example:
        log = get_trading_logger("XAUUSD")
        log.info("Trade executed")  # Will include epic in extra fields
    """
    return logger.bind(epic=epic)


def get_user_logger(user_id: int, username: str):
    """
    Get logger with user context.

    Args:
        user_id: User ID
        username: Username

    Returns:
        Logger with user context
    """
    return logger.bind(user_id=user_id, username=username)
