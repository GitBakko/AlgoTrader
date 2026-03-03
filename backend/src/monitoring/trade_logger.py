"""
Trade Logger - Structured logging for signals, executions, and risk decisions.

Logs all trading activity to PostgreSQL for analysis without stopping the backend.
Gracefully degrades to file logging if PostgreSQL unavailable.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from loguru import logger

from sqlalchemy import text as sa_text

from ..database.session import DatabaseManager


class SignalType(str, Enum):
    """Signal direction types."""
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


class ExecutionStatus(str, Enum):
    """Trade execution status."""
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXEC_FAILED = "exec_failed"
    HOLD = "hold"
    MARKET_CLOSED = "market_closed"


class RiskEventType(str, Enum):
    """Risk management event types."""
    CIRCUIT_BREAKER = "circuit_breaker"
    POSITION_LIMIT = "position_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    EQUITY_FILTER = "equity_filter"
    CONSECUTIVE_LOSS = "consecutive_loss"
    DAILY_LOSS = "daily_loss"


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Models for Structured Logs
# ═══════════════════════════════════════════════════════════════════════════


class SignalLog(BaseModel):
    """Signal generation log entry."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(default="unknown", description="Origin: paper_trading, demo_trading, live_trading, api_test")
    epic: str
    direction: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    strategy: str = Field(description="Strategy that generated signal")

    # Feature snapshot (JSON serializable dict)
    features: dict[str, float] = Field(default_factory=dict, description="Key features used")

    # ML model details
    model_version: str | None = None
    model_proba: dict[str, float] | None = Field(
        default=None,
        description="Class probabilities {LONG: 0.4, SHORT: 0.3, HOLD: 0.3}"
    )

    # Execution outcome (filled after trade attempt)
    execution_status: ExecutionStatus | None = None
    rejection_reason: str | None = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "timestamp": "2026-02-14T10:30:00Z",
            "epic": "XAUUSD",
            "direction": "LONG",
            "confidence": 0.72,
            "strategy": "ml_strategy",
            "features": {
                "rsi_14": 45.2,
                "macd_signal": 0.8,
                "bb_position": 0.3,
                "regime": "trending"
            },
            "model_version": "xgb_v1.2.0",
            "model_proba": {"LONG": 0.72, "SHORT": 0.15, "HOLD": 0.13},
            "execution_status": "executed",
            "rejection_reason": None
        }
    })


class ExecutionLog(BaseModel):
    """Trade execution log entry."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(default="unknown", description="Origin: paper_trading, demo_trading, live_trading, api_test")
    deal_id: str | None = None
    epic: str
    direction: str  # "BUY" or "SELL"
    size: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None

    # Execution details
    status: ExecutionStatus
    error_message: str | None = None

    # Position sizing details
    kelly_fraction: float | None = None
    risk_pct: float | None = None
    equity_at_entry: float | None = None

    # Exit details (filled on close)
    exit_price: float | None = None
    exit_timestamp: datetime | None = None
    realized_pnl: float | None = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "timestamp": "2026-02-14T10:30:05Z",
            "deal_id": "DEAL123456",
            "epic": "XAUUSD",
            "direction": "BUY",
            "size": 0.5,
            "entry_price": 2050.25,
            "stop_loss": 2045.00,
            "take_profit": 2060.00,
            "status": "executed",
            "error_message": None,
            "kelly_fraction": 0.15,
            "risk_pct": 2.0,
            "equity_at_entry": 10000.0,
            "exit_price": None,
            "exit_timestamp": None,
            "realized_pnl": None
        }
    })


class RiskEventLog(BaseModel):
    """Risk management decision log."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(default="unknown", description="Origin: paper_trading, demo_trading, live_trading, api_test")
    event_type: RiskEventType
    epic: str | None = None
    description: str

    # Risk metrics snapshot
    current_equity: float | None = None
    peak_equity: float | None = None
    current_drawdown_pct: float | None = None
    daily_pnl: float | None = None
    open_positions: int | None = None
    consecutive_losses: int | None = None

    # Action taken
    action: str = Field(description="Action taken (e.g., 'rejected_trade', 'halved_size', 'stopped_trading')")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "timestamp": "2026-02-14T10:30:10Z",
            "event_type": "circuit_breaker",
            "epic": "BTCUSD",
            "description": "Daily loss limit exceeded (-5.2%)",
            "current_equity": 9480.0,
            "peak_equity": 10000.0,
            "current_drawdown_pct": 5.2,
            "daily_pnl": -520.0,
            "open_positions": 2,
            "consecutive_losses": 4,
            "action": "stopped_trading"
        }
    })


# ═══════════════════════════════════════════════════════════════════════════
# TradeLogger Class
# ═══════════════════════════════════════════════════════════════════════════


class TradeLogger:
    """
    Structured logger for trading activity.

    Logs to PostgreSQL tables (signal_log, execution_log, risk_event_log).
    Falls back to JSON file logging if PostgreSQL unavailable.
    """

    def __init__(self, log_dir: Path | None = None):
        """
        Initialize trade logger.

        Args:
            log_dir: Directory for fallback JSON logs (default: data/logs/)
        """
        self.log_dir = log_dir or Path("data/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Fallback file paths
        self.signal_log_file = self.log_dir / "signals.jsonl"
        self.execution_log_file = self.log_dir / "executions.jsonl"
        self.risk_log_file = self.log_dir / "risk_events.jsonl"

        logger.info(f"TradeLogger initialized with log_dir={self.log_dir}")

    async def log_signal(
        self,
        epic: str,
        direction: SignalType,
        confidence: float,
        strategy: str,
        features: dict[str, float] | None = None,
        model_version: str | None = None,
        model_proba: dict[str, float] | None = None,
        execution_status: ExecutionStatus | None = None,
        rejection_reason: str | None = None,
        source: str = "unknown",
    ) -> None:
        """
        Log a trading signal.

        Args:
            epic: Asset symbol
            direction: Signal direction (LONG/SHORT/HOLD)
            confidence: Signal confidence [0.0, 1.0]
            strategy: Strategy name that generated signal
            features: Dictionary of key features used
            model_version: ML model version (if applicable)
            model_proba: Class probabilities from model
            execution_status: Execution outcome (if known)
            rejection_reason: Reason for rejection (if applicable)
            source: Origin of signal (paper_trading, demo_trading, live_trading, api_test)
        """
        signal = SignalLog(
            epic=epic,
            direction=direction,
            confidence=confidence,
            strategy=strategy,
            features=features or {},
            model_version=model_version,
            model_proba=model_proba,
            execution_status=execution_status,
            rejection_reason=rejection_reason,
            source=source,
        )

        await self._write_log("signal_log", signal)
        logger.debug(f"[SIGNAL] {epic} {direction.value} conf={confidence:.2f} strategy={strategy}")

    async def log_execution(
        self,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        status: ExecutionStatus,
        deal_id: str | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        error_message: str | None = None,
        kelly_fraction: float | None = None,
        risk_pct: float | None = None,
        equity_at_entry: float | None = None,
        source: str = "unknown",
    ) -> None:
        """
        Log a trade execution.

        Args:
            epic: Asset symbol
            direction: "BUY" or "SELL"
            size: Position size
            entry_price: Entry price
            status: Execution status
            deal_id: Broker deal ID (if executed)
            stop_loss: Stop loss level
            take_profit: Take profit level
            error_message: Error message (if failed)
            kelly_fraction: Kelly fraction used
            risk_pct: Risk percentage
            equity_at_entry: Account equity at entry
            source: Origin of execution (paper_trading, demo_trading, live_trading, api_test)
        """
        execution = ExecutionLog(
            deal_id=deal_id,
            epic=epic,
            direction=direction,
            size=size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status=status,
            error_message=error_message,
            kelly_fraction=kelly_fraction,
            risk_pct=risk_pct,
            equity_at_entry=equity_at_entry,
            source=source,
        )

        await self._write_log("execution_log", execution)
        logger.info(
            f"[EXECUTION] {epic} {direction} {size:.4f} @ {entry_price:.2f} "
            f"status={status.value} deal_id={deal_id}"
        )

        # Fire alert for trade executions in DEMO/LIVE mode
        if status == ExecutionStatus.EXECUTED and source in ("demo_trading", "live_trading"):
            try:
                from src.monitoring.alerting.alert_manager import get_alert_manager
                from src.utils.config import get_settings
                if getattr(get_settings(), "alerts_enabled", False):
                    am = get_alert_manager()
                    await am.alert_trade_opened(
                        epic=epic,
                        direction=direction,
                        size=size,
                        entry_price=entry_price,
                        deal_id=deal_id or "UNKNOWN",
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                    )
            except Exception as alert_err:
                logger.debug(f"Trade open alert failed (non-critical): {alert_err}")

    async def log_risk_decision(
        self,
        event_type: RiskEventType,
        description: str,
        action: str,
        epic: str | None = None,
        current_equity: float | None = None,
        peak_equity: float | None = None,
        current_drawdown_pct: float | None = None,
        daily_pnl: float | None = None,
        open_positions: int | None = None,
        consecutive_losses: int | None = None,
        source: str = "unknown",
    ) -> None:
        """
        Log a risk management decision.

        Args:
            event_type: Type of risk event
            description: Human-readable description
            action: Action taken
            epic: Asset symbol (if applicable)
            current_equity: Current account equity
            peak_equity: Peak equity
            current_drawdown_pct: Current drawdown percentage
            daily_pnl: Daily P&L
            open_positions: Number of open positions
            consecutive_losses: Consecutive loss count
            source: Origin of event (paper_trading, demo_trading, live_trading, api_test)
        """
        risk_event = RiskEventLog(
            event_type=event_type,
            epic=epic,
            description=description,
            current_equity=current_equity,
            peak_equity=peak_equity,
            current_drawdown_pct=current_drawdown_pct,
            daily_pnl=daily_pnl,
            open_positions=open_positions,
            consecutive_losses=consecutive_losses,
            action=action,
            source=source,
        )

        await self._write_log("risk_event_log", risk_event)
        logger.warning(
            f"[RISK] {event_type.value} - {description} → {action}"
        )

        # Fire alert for circuit breaker events
        if event_type == RiskEventType.CIRCUIT_BREAKER:
            try:
                from src.monitoring.alerting.alert_manager import get_alert_manager
                from src.utils.config import get_settings
                if getattr(get_settings(), "alerts_enabled", False):
                    am = get_alert_manager()
                    await am.alert_circuit_breaker(
                        epic=epic or "GLOBAL",
                        reason=description,
                        consecutive_losses=consecutive_losses or 0,
                    )
            except Exception as alert_err:
                logger.debug(f"Circuit breaker alert failed (non-critical): {alert_err}")

    async def _write_log(
        self,
        table_name: str,
        log_entry: SignalLog | ExecutionLog | RiskEventLog
    ) -> None:
        """
        Write log entry to PostgreSQL or fallback to JSON file.

        Args:
            table_name: PostgreSQL table name
            log_entry: Log entry to write
        """
        try:
            # Try PostgreSQL first
            async with DatabaseManager.session() as session:
                # Use mode="json" for clean serialisation, then fix types for asyncpg
                data = log_entry.model_dump(mode="json")

                # asyncpg needs native datetime, not ISO strings
                for key, val in data.items():
                    if isinstance(val, str) and key.endswith(("timestamp", "_at")):
                        try:
                            data[key] = datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
                        except (ValueError, AttributeError):
                            pass

                # Convert remaining datetime objects (strip tz)
                for key, val in data.items():
                    if isinstance(val, datetime):
                        data[key] = val.replace(tzinfo=None)

                # Convert dicts/lists to JSON strings for TEXT columns
                import json as _json
                for key, val in data.items():
                    if isinstance(val, (dict, list)):
                        data[key] = _json.dumps(val)

                # Build INSERT statement dynamically
                columns = ", ".join(data.keys())
                placeholders = ", ".join([f":{k}" for k in data.keys()])
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

                await session.execute(sa_text(query), data)

        except Exception as e:
            logger.warning(f"PostgreSQL write failed for {table_name}, falling back to file: {e}")
            await self._write_to_file(table_name, log_entry)

    async def _write_to_file(
        self,
        table_name: str,
        log_entry: SignalLog | ExecutionLog | RiskEventLog
    ) -> None:
        """
        Write log entry to JSONL file (fallback).

        Args:
            table_name: Determines which file to write to
            log_entry: Log entry to write
        """
        file_map = {
            "signal_log": self.signal_log_file,
            "execution_log": self.execution_log_file,
            "risk_event_log": self.risk_log_file,
        }

        log_file = file_map.get(table_name)
        if not log_file:
            logger.error(f"Unknown table name: {table_name}")
            return

        # Append to JSONL file (one JSON object per line)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry.model_dump_json() + "\n")


# ═══════════════════════════════════════════════════════════════════════════
# Global TradeLogger Instance
# ═══════════════════════════════════════════════════════════════════════════

# Singleton instance for easy import
_trade_logger: TradeLogger | None = None


def get_trade_logger() -> TradeLogger:
    """Get global TradeLogger instance (singleton)."""
    global _trade_logger
    if _trade_logger is None:
        _trade_logger = TradeLogger()
    return _trade_logger
