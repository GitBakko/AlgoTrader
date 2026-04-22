"""
Paper trading loop.
Background task that checks for new 1h candles every 5 minutes and runs
the full ML prediction -> execution pipeline when new data is detected.

Phase 8 integration:
- TrailingStopManager: register on open, update_price each iteration, partial_close at TP1
- CircuitBreakers: heartbeat each iteration, record_trade_result on close
- EquityCurveFilter: record_trade_close on position close
- Kelly sizing: pass trade history to risk_manager.check_trade()
"""

import asyncio
import time as _time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from loguru import logger

from src.broker.client import CapitalComClient
from src.data.data_access import DataAccessLayer
from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.external.sil_schemas import SILData
from src.models.prediction_service import PredictionService
from src.monitoring.metrics import MetricsCollector
from src.monitoring.trade_logger import ExecutionStatus, RiskEventType, SignalType, get_trade_logger
from src.risk.asset_performance_tracker import AssetPerformanceTracker
from src.risk.risk_manager import RiskManager
from src.risk.stop_manager import StopManager
from src.risk.trailing_stop_manager import TrailingPhase, TrailingStopConfig, TrailingStopManager
from src.strategy.schemas import SignalDirection
from src.strategy.strategy_manager import StrategyManager
from src.utils.config import get_settings
from src.utils.constants import TRADABLE_ASSETS


@dataclass
class PendingClose:
    """A position that disappeared from broker but whose close transaction
    has not yet been matched. Held in memory for retry during subsequent
    loop iterations, up to Settings.close_reconciliation_timeout_seconds.
    """

    deal_id: str
    deal_reference: str | None
    epic: str
    direction: str
    size: float
    entry_price: float
    prev_pos: dict
    first_seen: datetime
    retry_count: int = 0


# How often to check for new candles (seconds)
_settings = get_settings()
CHECK_INTERVAL = (
    _settings.scalp_check_interval
    if (_settings.scalp_mode_enabled or _settings.mr_primary_enabled)
    else 300
)
MAX_SIGNAL_HISTORY = 200


def _recalculate_sl_tp_from_fill(
    direction: str,
    fill_price: float,
    atr: float,
    stop_multiplier: float,
    risk_reward: float,
) -> tuple[float, float]:
    """Recalculate SL/TP from actual fill price (not candle close)."""
    sl = StopManager.calculate_stop_loss(direction, fill_price, atr, stop_multiplier)
    tp = StopManager.calculate_take_profit(direction, fill_price, atr, stop_multiplier, risk_reward)
    return sl, tp


def _validate_sl_side(direction: str, entry: float, sl: float) -> bool:
    """Validate that SL is on the correct side of entry price."""
    if direction == "BUY":
        return sl < entry
    return sl > entry  # SELL: SL must be above entry


def _validate_tp_side(direction: str, entry: float, tp: float) -> bool:
    """Validate that TP is on the correct side of entry price."""
    if direction == "BUY":
        return tp > entry
    return tp < entry  # SELL: TP must be below entry


class PaperTradingLoop:
    """
    Controllable background loop that runs paper trading iterations.

    Checks every 5 minutes for new 1h candles. When a new candle is detected
    for any epic, it runs the full prediction pipeline for that epic only.

    Each iteration:
    1. Check if new 1h candle available (compare timestamps)
    2. PredictionService.predict() for each epic with new data
    3. StrategyManager.process_prediction() -> TradingSignal
    4. RiskManager.check_trade() -> RiskCheckResult
    5. ExecutionEngine.execute_signal() (paper mode) -> ExecutionResult
    """

    def __init__(
        self,
        prediction_service: PredictionService,
        strategy_manager: StrategyManager,
        risk_manager: RiskManager,
        execution_engine: ExecutionEngine,
        data_access: DataAccessLayer | None = None,
        broker: CapitalComClient | None = None,
        interval_seconds: int = CHECK_INTERVAL,
        epics: list[str] | None = None,
        trailing_stop_config: TrailingStopConfig | None = None,
        db_session_factory=None,
        trailing_stop_manager: TrailingStopManager | None = None,
        signal_repo_factory=None,
    ):
        self.prediction_service = prediction_service
        self.strategy_manager = strategy_manager
        self.risk_manager = risk_manager
        self.execution_engine = execution_engine
        self.data_access = data_access
        self.broker = broker
        self.interval_seconds = interval_seconds
        self.epics = epics or list(TRADABLE_ASSETS)

        # Derive log source from execution mode
        from src.execution.schemas import ExecutionMode

        mode = execution_engine.mode if execution_engine else ExecutionMode.PAPER
        self._log_source = {
            ExecutionMode.PAPER: "paper_trading",
            ExecutionMode.DEMO: "demo_trading",
            ExecutionMode.LIVE: "live_trading",
        }.get(mode, "paper_trading")

        # Phase 8/14: trailing stop manager (use recovered one or create new)
        self.trailing_stop_manager = trailing_stop_manager or TrailingStopManager(
            trailing_stop_config
        )
        # In-memory trade history for Kelly sizing (last 200 trades, auto-discards old entries)
        self._trade_history: deque[dict] = deque(maxlen=200)
        # Phase 14: database session factory for state persistence
        self._db_session_factory = db_session_factory
        # Decision audit trail: signal persistence factory
        self._signal_repo_factory = signal_repo_factory
        # Rolling per-asset performance tracker (14-day Sharpe exclusion)
        _init_settings = get_settings()
        self._asset_tracker = AssetPerformanceTracker(
            lookback_days=_init_settings.scalp_asset_exclusion_lookback_days,
            min_trades=_init_settings.scalp_asset_exclusion_min_trades,
            sharpe_threshold=_init_settings.scalp_asset_exclusion_sharpe_threshold,
        )

        self._running = False
        self._task: asyncio.Task | None = None
        self._last_run: datetime | None = None
        self._iteration_count = 0
        self._check_count = 0
        self._trade_count = 0
        self._signal_count = 0
        self._error_count = 0

        # HIGH-7 FIX: Track recently processed signals to prevent duplicates
        # Format: (epic, direction, entry_price_rounded) -> timestamp
        self._recent_signals: dict[tuple[str, str, float], datetime] = {}
        self._signal_dedup_window_seconds = (
            _settings.scalp_signal_dedup_seconds if _settings.scalp_mode_enabled else 60
        )
        # Candle resolution: scalp_candle_resolution for scalp/MR, 1h fallback for legacy ML
        # Both scalp and MR_PRIMARY use the configured resolution (e.g. 4h for MR)
        if _settings.scalp_mode_enabled or _settings.mr_primary_enabled:
            self._candle_resolution = _settings.scalp_candle_resolution
        else:
            self._candle_resolution = "1h"
        self._last_signals: dict[str, dict] = {}
        self._signal_history: deque[dict] = deque(maxlen=MAX_SIGNAL_HISTORY)
        # Track last processed candle timestamp per epic
        self._last_candle_ts: dict[str, datetime] = {}
        # Market info cache (avoid repeated API calls)
        self._market_info_cache: dict[str, dict] = {}
        self._market_cache_ttl = 3600  # 1 hour
        self._market_cache_ts: dict[str, float] = {}
        # Dedicated min deal size cache (seeded from DB at startup, updated per-iteration)
        self._min_deal_size_cache: dict[str, float] = {}
        # Regime distribution tracking per epic (Step 7: regime detection)
        self._regime_counts: dict[str, dict[str, int]] = {}
        # Track positions from previous iteration to detect broker-closed positions
        self._previous_positions: dict[str, dict] = {}
        # Positions that disappeared from broker but whose close transaction has not
        # yet been matched — keyed by deal_id, held until reconciliation or timeout.
        self._pending_close_detections: dict[str, PendingClose] = {}
        # Close-detection v2 (shadow mode). Instantiated lazily on first tick
        # where CLOSE_DETECTION_V2_ENABLED is True so test suites and PAPER
        # mode paths never pay the FX/broker construction cost.
        self._close_detector = None
        self._account_currency: str = "USD"
        # Asset momentum rotation
        self._active_assets: set[str] | None = None  # None = all assets
        self._asset_rotation_ts: float = 0.0
        self._per_asset_losses: dict[str, int] = {}  # consecutive loss counter per asset
        self._spread_blocked_epics: dict[str, dict] = {}  # epic → spread block info
        # deal_id -> {requested_sl, requested_tp, actual_sl, actual_tp, sl_dev, tp_dev}
        # Tracks the difference between what we requested at order creation and
        # what the broker actually applied (due to min-distance constraints).
        self._level_deviations: dict[str, dict] = {}
        self._last_spread_refresh: float = 0.0  # timestamp of last hourly spread check
        self._correlation_regime: str = "normal"
        self._correlation_regime_ts: float = 0.0

        # Regime Gate (Phase 2)
        self._regime_gate: object | None = None
        self._regime_gate_feature_cols: list[str] = []

        # Epic SL cooldown tracker: epic → list of SL hit timestamps (UTC)
        self._epic_sl_hits: dict[str, list[datetime]] = {}
        self._epic_sl_window_hours = 2.0  # cooldown window
        self._epic_sl_max_strikes = 3  # strikes before blocking

        # Signal Intelligence Layer (SIL)
        self._sil_data: SILData = SILData()
        self._sil_clients_initialized = False
        self._calendar_gate = None
        if _settings.sil_enabled:
            self._init_sil_clients()

        # MANTIS-EVOLUTION: Multi-agent orchestrator (optional, feature-flag gated)
        self._agents_enabled = _init_settings.agents_enabled
        self._orchestrator = None
        if self._agents_enabled:
            try:
                from src.agents.orchestrator import MantisAgentOrchestrator

                self._orchestrator = MantisAgentOrchestrator(
                    vision_enabled=_init_settings.vision_enabled,
                    drl_enabled=_init_settings.drl_enabled,
                )
                logger.info("Multi-agent orchestrator initialized")
            except Exception as e:
                logger.warning(f"Orchestrator init failed: {e!r} — agents disabled")
                self._agents_enabled = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    @property
    def iteration_count(self) -> int:
        return self._iteration_count

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def signal_count(self) -> int:
        return self._signal_count

    @property
    def last_signals(self) -> dict[str, dict]:
        """Last signal info per epic (read-only copy)."""
        return dict(self._last_signals)

    def _init_sil_clients(self) -> None:
        """Initialize SIL external clients and calendar gate."""
        try:
            from src.external.alpha_vantage_client import AlphaVantageClient
            from src.external.cot_client import COTClient
            from src.external.fear_greed_client import FearGreedClient
            from src.external.fred_client import FREDClient
            from src.external.social_sentiment_client import SocialSentimentClient
            from src.risk.economic_calendar_gate import EconomicCalendarGate

            self._fg_client = FearGreedClient()
            self._fred_client = FREDClient()
            self._av_client = AlphaVantageClient()
            self._cot_client = COTClient()
            self._social_client = SocialSentimentClient()
            self._calendar_gate = EconomicCalendarGate()
            self._sil_clients_initialized = True
            logger.info("[SIL] Signal Intelligence Layer clients initialized")
        except Exception as e:
            logger.warning(f"[SIL] Failed to initialize clients: {e}")
            self._sil_clients_initialized = False

    async def _fetch_sil_data(self) -> SILData:
        """Fetch all SIL data with per-client error handling."""
        if not self._sil_clients_initialized:
            return SILData()

        errors: list[str] = []
        fg_data = None
        fred_data = None
        av_data = None
        cot_data = None
        social_data = None

        # Fetch all clients concurrently
        async def _safe(name, coro):
            try:
                return await coro
            except Exception as e:
                errors.append(f"{name}: {e}")
                logger.debug(f"[SIL] {name} fetch failed: {e}")
                return None

        results = await asyncio.gather(
            _safe("FearGreed", self._fg_client.fetch()),
            _safe("FRED", self._fred_client.fetch()),
            _safe("AlphaVantage", self._av_client.fetch()),
            _safe("COT", self._cot_client.fetch("XAUUSD")),
            _safe("Social", self._social_client.fetch("XAUUSD")),
            return_exceptions=False,
        )

        fg_data, fred_data, av_data, cot_data, social_data = results

        from src.external.sil_schemas import (
            AlphaVantageData,
            COTData,
            FearGreedData,
            FREDData,
            SocialSentimentData,
        )

        sil = SILData(
            fear_greed=fg_data or FearGreedData(),
            fred=fred_data or FREDData(),
            alpha_vantage=av_data or AlphaVantageData(),
            cot=cot_data or COTData(),
            social=social_data or SocialSentimentData(),
            fetch_errors=errors,
        )

        if errors:
            logger.warning(f"[SIL] {len(errors)} fetch errors: {errors}")
        else:
            logger.info("[SIL] All data fetched successfully")

        return sil

    async def get_positions_async(self) -> list[dict]:
        """Get positions for all modes (async, works with broker or in-memory).

        Enriches each position with trailing_stop_phase from TrailingStopManager.
        """
        positions = await self.execution_engine.get_open_positions()
        for pos in positions:
            deal_id = pos.get("deal_id", "")
            state = self.trailing_stop_manager.get_state(deal_id)
            if state is None:
                # Try matching by epic (broker deal_ids can differ)
                for tracked_id in self.trailing_stop_manager.tracked_positions:
                    ts = self.trailing_stop_manager.get_state(tracked_id)
                    if ts and ts.epic == pos.get("epic"):
                        state = ts
                        break
            if state:
                from src.risk.trailing_stop_manager import TrailingPhase

                pos["trailing_stop_phase"] = TrailingPhase(state.phase).name

            # Attach level deviation info (requested vs broker-actual SL/TP)
            deviation = self._level_deviations.get(deal_id)
            if deviation is None:
                # Fallback: match by epic if deal_id differs (Capital.com quirk)
                for tracked_id, dev in self._level_deviations.items():
                    if pos.get("epic") and tracked_id.startswith(pos.get("epic", "")):
                        deviation = dev
                        break
            if deviation:
                pos["level_deviation"] = deviation
        return positions

    def get_paper_positions(self) -> list[dict]:
        """Get paper positions (sync, PAPER mode only, for backward compat)."""
        if self.execution_engine.mode == ExecutionMode.PAPER:
            return self.execution_engine._position_tracker.get_paper_positions_sync()
        return []

    def get_signal_history(self) -> list[dict]:
        """Get signal history as a list (public accessor, defensive copy)."""
        return list(self._signal_history)

    async def _persist_risk_state(self) -> None:
        """
        Persist current RiskManager state to database.
        Saves DrawdownMonitor, CircuitBreakers, and EquityCurveFilter state.
        """
        if self._db_session_factory is None:
            return  # No database available, skip persistence

        try:
            from decimal import Decimal

            from src.database.repositories import RiskStateRepository

            async with self._db_session_factory() as session:
                repo = RiskStateRepository(session)

                # Extract state from RiskManager components
                dm_state = self.risk_manager.drawdown_monitor.state
                cb_state = self.risk_manager.circuit_breakers
                ec_state = self.risk_manager.equity_curve_filter

                # Tripped breakers: {breaker_type: reason_string}
                tripped_breakers_serialized = dict(cb_state.tripped_breakers)

                # Equity curve: keep last 50 points
                equity_curve_points = list(ec_state._equity_points)[-50:]

                await repo.create_snapshot(
                    peak_equity=Decimal(str(dm_state.peak_equity)),
                    daily_start_equity=Decimal(str(dm_state.daily_start_equity)),
                    current_equity=Decimal(str(dm_state.current_equity)),
                    consecutive_losses=cb_state._consecutive_losses,
                    tripped_breakers=tripped_breakers_serialized,
                    equity_curve_points=equity_curve_points,
                )
                await session.commit()
                logger.debug("Persisted risk state to database")
        except Exception as e:
            logger.warning(f"Risk state persistence failed: {e}")

    async def _persist_position_open(
        self,
        deal_id: str,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        stop_loss: float | None,
        take_profit: float | None,
        deal_reference: str | None = None,
    ) -> None:
        """Persist a newly opened position to the database."""
        if self._db_session_factory is None:
            return

        try:
            from decimal import Decimal

            from src.database.models import Position, Trade
            from src.database.repositories import PositionRepository

            async with self._db_session_factory() as session:
                repo = PositionRepository(session)

                # Check for existing (idempotency)
                existing = await repo.get_by_deal_id(deal_id)
                if existing:
                    logger.debug(f"Position {deal_id} already in DB, skipping")
                    await session.commit()
                    return

                pos = Position(
                    deal_id=deal_id,
                    deal_reference=deal_reference,
                    epic=epic,
                    direction=direction,
                    size=Decimal(str(size)),
                    entry_price=Decimal(str(entry_price)),
                    stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                    take_profit=Decimal(str(take_profit)) if take_profit else None,
                    status="OPEN",
                    opened_at=datetime.now(UTC).replace(tzinfo=None),
                )
                pos = await repo.create(pos)

                # Also create an OPEN trade record
                trade = Trade(
                    position_id=pos.id,
                    deal_reference=deal_id,
                    trade_type="OPEN",
                    epic=epic,
                    direction=direction,
                    size=Decimal(str(size)),
                    price=Decimal(str(entry_price)),
                    executed_at=datetime.now(UTC).replace(tzinfo=None),
                )
                session.add(trade)
                await session.commit()
                logger.debug(f"Persisted OPEN position to DB: {deal_id} ({epic} {direction})")
        except Exception as e:
            logger.warning(f"Position open persistence failed for {deal_id}: {e}")

    async def _persist_position_close(
        self,
        deal_id: str,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        exit_price: float,
        pnl: float | None,
        close_reason: str,
        opened_at: datetime | None = None,
    ) -> None:
        """Persist position close to the database (update status + create CLOSE trade).

        `pnl` may be None on the UNRECONCILED path (Tier 3 fail-safe) — in that
        case we store NULL for both Position.profit_loss and Trade.profit_loss
        so aggregate stats (see repository filters) can correctly skip the row.
        """
        if self._db_session_factory is None:
            return

        # Normalize close_reason to short form expected by frontend
        reason_map = {
            "STOP_LOSS_HIT": "SL",
            "TAKE_PROFIT_HIT": "TP",
            "TP1_HIT": "TP",
            "TIME_STOP": "TIME",
            "API close request": "MANUAL",
            "Graceful shutdown": "MANUAL",
        }
        close_reason = reason_map.get(close_reason, close_reason)
        pnl_repr = f"{pnl:.2f}" if pnl is not None else "NULL"

        try:
            from decimal import Decimal

            from src.database.models import Position, Trade
            from src.database.repositories import PositionRepository

            pnl_decimal = Decimal(str(round(pnl, 2))) if pnl is not None else None

            async with self._db_session_factory() as session:
                repo = PositionRepository(session)
                pos = await repo.get_by_deal_id(deal_id)

                if pos is None:
                    # Position was never persisted at open — create it as CLOSED
                    now = datetime.now(UTC).replace(tzinfo=None)
                    actual_opened = opened_at or now
                    if isinstance(actual_opened, str):
                        try:
                            parsed = datetime.fromisoformat(actual_opened)
                            # Convert to UTC if timezone-aware, then strip tzinfo
                            if parsed.tzinfo is not None:
                                parsed = parsed.astimezone(UTC)
                            actual_opened = parsed.replace(tzinfo=None)
                        except (ValueError, TypeError):
                            actual_opened = now
                    elif hasattr(actual_opened, "tzinfo") and actual_opened.tzinfo is not None:
                        actual_opened = actual_opened.astimezone(UTC).replace(tzinfo=None)

                    # Guard: opened_at must never be after closed_at
                    if actual_opened > now:
                        logger.warning(
                            f"Position {deal_id}: opened_at ({actual_opened}) > "
                            f"closed_at ({now}), correcting to closed_at"
                        )
                        actual_opened = now

                    pos = Position(
                        deal_id=deal_id,
                        epic=epic,
                        direction=direction,
                        size=Decimal(str(size)),
                        entry_price=Decimal(str(entry_price)),
                        current_price=Decimal(str(exit_price)),
                        profit_loss=pnl_decimal,
                        stop_loss=None,
                        take_profit=None,
                        status="CLOSED",
                        opened_at=actual_opened,
                        closed_at=now,
                        close_reason=close_reason,
                    )
                    pos = await repo.create(pos)
                else:
                    # Update existing
                    now = datetime.now(UTC).replace(tzinfo=None)
                    pos.status = "CLOSED"
                    pos.current_price = Decimal(str(exit_price))
                    pos.profit_loss = pnl_decimal
                    pos.closed_at = now
                    pos.close_reason = close_reason
                    # Guard: correct opened_at if it's somehow after closed_at
                    if pos.opened_at and pos.opened_at > now:
                        logger.warning(
                            f"Position {deal_id}: DB opened_at ({pos.opened_at}) > "
                            f"closed_at ({now}), correcting"
                        )
                        pos.opened_at = now
                    await session.flush()
                    await session.refresh(pos)

                # Create CLOSE trade record
                trade = Trade(
                    position_id=pos.id,
                    deal_reference=deal_id,
                    trade_type="CLOSE",
                    epic=epic,
                    direction=direction,
                    size=Decimal(str(size)),
                    price=Decimal(str(exit_price)),
                    profit_loss=pnl_decimal,
                    executed_at=datetime.now(UTC).replace(tzinfo=None),
                )
                session.add(trade)
                await session.commit()
                logger.info(
                    f"Persisted CLOSED position to DB: {deal_id} ({epic} P&L={pnl_repr} reason={close_reason})"
                )
        except Exception as e:
            logger.warning(f"Position close persistence failed for {deal_id}: {e}")

    def _init_regime_gate(self) -> None:
        """Initialize RegimeGate if enabled and not already initialized."""
        if self._regime_gate is not None:
            return
        _settings = get_settings()
        if not _settings.regime_gate_enabled:
            return

        try:
            from src.regime.gate import RegimeGate

            self._regime_gate = RegimeGate(
                confidence_threshold=_settings.regime_gate_confidence_threshold,
                psi_threshold=_settings.regime_gate_psi_threshold,
            )

            # Load pre-trained detectors if available
            import json
            from pathlib import Path

            from src.regime.drift_monitor import DriftMonitor
            from src.regime.hmm_detector import HMMRegimeDetector

            for epic in self.epics:
                hmm_path = Path(f"data/models/{epic}/regime/hmm_detector.pkl")
                drift_path = Path(f"data/models/{epic}/regime/drift_monitor.pkl")
                features_path = Path(f"data/models/{epic}/regime/drift_features.json")
                if hmm_path.exists():
                    try:
                        self._regime_gate.hmm_detector = HMMRegimeDetector.load(hmm_path)
                        if drift_path.exists():
                            self._regime_gate.drift_monitor = DriftMonitor.load(
                                drift_path, _settings.regime_gate_psi_threshold
                            )
                        if features_path.exists():
                            with open(features_path) as f:
                                self._regime_gate_feature_cols = json.load(f)
                        logger.info(f"Loaded regime detector from {epic}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to load regime detector for {epic}: {e}")

            logger.info(
                f"RegimeGate initialized "
                f"(confidence>{_settings.regime_gate_confidence_threshold}, "
                f"PSI<{_settings.regime_gate_psi_threshold})"
            )
        except Exception as e:
            logger.warning(f"RegimeGate init failed: {e}")

    async def _read_broker_stops(
        self, deal_id: str, epic: str | None = None
    ) -> tuple[float | None, float | None]:
        """Read the current SL/TP from the broker for a position.

        Capital.com may return a different deal_id from create vs list, so
        we also try matching by epic as a fallback.
        """
        if not self.broker:
            return None, None
        try:
            positions = await self.broker.list_positions()
            for p in positions:
                if p.deal_id == deal_id:
                    return p.stop_level, p.profit_level
            # Fallback: match by epic
            if epic:
                for p in positions:
                    if p.epic == epic:
                        return p.stop_level, p.profit_level
        except Exception as e:
            logger.debug(f"_read_broker_stops failed: {e}")
        return None, None

    async def _refresh_correlation_regime(self) -> None:
        """Recompute correlation regime every 30 minutes."""
        now = _time.monotonic()
        if now - self._correlation_regime_ts < 1800:
            return
        self._correlation_regime_ts = now

        _settings = get_settings()
        if not _settings.correlation_regime_enabled:
            return

        try:
            from src.features.cross_asset import CrossAssetEngine

            engine = CrossAssetEngine()
            all_dfs = {}
            for epic in self.epics[:10]:
                try:
                    df = self.data_access.get_candles(epic, self._candle_resolution)
                    if df is not None and len(df) >= 100:
                        all_dfs[epic] = df
                except Exception:
                    pass

            if len(all_dfs) >= 5:
                regime_df = engine.compute_correlation_regime(all_dfs, window=50)
                if len(regime_df) > 0:
                    last = regime_df.row(-1, named=True)
                    self._correlation_regime = last.get("correlation_regime") or "normal"
                    mean_corr = last.get("mean_correlation", 0)
                    logger.info(
                        f"Correlation regime: {self._correlation_regime} " f"(mean={mean_corr:.3f})"
                    )

                    # Also update CorrelationGuard's dynamic matrix
                    try:
                        epics_list = sorted(all_dfs.keys())
                        common_len = min(len(df) for df in all_dfs.values())
                        returns = np.array(
                            [
                                np.diff(
                                    np.log(
                                        np.maximum(
                                            all_dfs[e]["close"].tail(common_len).to_numpy(),
                                            1e-10,
                                        )
                                    )
                                )
                                for e in epics_list
                            ]
                        )
                        corr_matrix = np.corrcoef(returns)
                        self.risk_manager.correlation_guard.update_matrix(epics_list, corr_matrix)
                        logger.debug(f"Updated CorrelationGuard matrix: {len(epics_list)} assets")
                    except Exception as e:
                        logger.debug(f"CorrelationGuard matrix update failed: {e}")
        except Exception as e:
            logger.debug(f"Correlation regime update failed: {e}")

    async def _refresh_spread_blocks(self) -> None:
        """Re-evaluate spread-blocked epics every hour.

        Queries current bid/offer for each blocked epic and unblocks
        those whose spread has come back within MAX_SPREAD_PCT of TP distance.
        """
        now = _time.monotonic()
        if now - self._last_spread_refresh < 3600:  # 1 hour
            return
        self._last_spread_refresh = now

        if not self._spread_blocked_epics or not self.broker:
            return

        _settings = get_settings()
        if _settings.max_spread_pct <= 0:
            return

        _tp_rr = _settings.scalp_tp_risk_reward if _settings.scalp_mode_enabled else 2.5
        unblocked = []

        for epic in list(self._spread_blocked_epics.keys()):
            try:
                market = await self.broker.get_market_details(epic)
                snapshot = market.get("snapshot", {})
                bid = snapshot.get("bid", 0)
                offer = snapshot.get("offer", 0)
                if not bid or not offer:
                    continue

                spread = offer - bid
                # Get ATR for TP distance estimate
                market_data = self.prediction_service.get_market_data(
                    epic, timeframe=self._candle_resolution
                )
                if not market_data or market_data.get("atr", 0) <= 0:
                    continue

                tp_distance = market_data["atr"] * _tp_rr
                spread_ratio = spread / tp_distance if tp_distance > 0 else 1.0

                if spread_ratio <= _settings.max_spread_pct:
                    unblocked.append(epic)
                    logger.info(
                        f"[{epic}] Spread improved: {spread_ratio:.1%} <= "
                        f"{_settings.max_spread_pct:.0%} limit — unblocked"
                    )
                else:
                    # Update stored spread info
                    self._spread_blocked_epics[epic]["spread"] = round(spread, 8)
                    self._spread_blocked_epics[epic]["spread_pct"] = round(spread_ratio * 100, 1)
            except Exception as e:
                logger.debug(f"[{epic}] Spread refresh failed: {e}")

        for epic in unblocked:
            del self._spread_blocked_epics[epic]

        if unblocked:
            logger.info(f"Spread refresh: unblocked {unblocked}")
        elif self._spread_blocked_epics:
            logger.debug(
                f"Spread refresh: {list(self._spread_blocked_epics.keys())} " f"still blocked"
            )

    async def _fetch_recent_transactions(self) -> list:
        """Fetch recent transaction history from Capital.com for close detection.

        Returns list of Transaction objects from the last 4 hours.
        Uses a cache to avoid hammering the API on every loop iteration.
        """
        now = datetime.now(UTC)
        # Cache transactions for 30 seconds to avoid excessive API calls
        cache_attr = "_txn_cache"
        cache_ts_attr = "_txn_cache_ts"
        cached = getattr(self, cache_attr, None)
        cached_ts = getattr(self, cache_ts_attr, None)
        if cached is not None and cached_ts and (now - cached_ts).total_seconds() < 60:
            return cached

        try:
            from src.broker.models import TransactionType

            from_date = now - timedelta(hours=24)
            transactions = await self.broker.get_transaction_history(
                from_date, now, TransactionType.TRADE
            )
            setattr(self, cache_attr, transactions)
            setattr(self, cache_ts_attr, now)
            return transactions
        except Exception as e:
            logger.warning(f"Failed to fetch transaction history: {e}")
            return []

    @staticmethod
    def _normalize_instrument_name(name: str) -> str:
        """Normalize instrument/epic names for fuzzy matching.

        Strips underscores, hyphens, whitespace; lowercases; keeps only alphanumerics.
        'OIL_CRUDE' → 'oilcrude', 'Oil - Crude' → 'oilcrude', 'Germany 40' → 'germany40'.
        """
        return "".join(ch for ch in (name or "").lower() if ch.isalnum())

    def _match_transaction(
        self,
        transactions: list,
        deal_id: str,
        deal_reference: str | None,
        epic: str,
        entry_price: float,
    ) -> tuple[float | None, float | None, str | None]:
        """Match a closed deal to a broker Transaction by deterministic keys only.

        Strategy 1 (dealId):    `txn.deal_id == deal_id` — current Capital.com
                                live schema exposes the Position deal_id on
                                each TRADE row.
        Strategy 2 (reference): `txn.reference == deal_reference` or `deal_id`.
                                Legacy fallback for older response payloads
                                where the deal_id was stored in `reference`.

        The previous Strategy 3 fuzzy match (normalized instrument name +
        entry-price tolerance) was deleted in Step 8 of close-detection v2:
        (1) it routinely matched ghost positions on the same epic — see memory
        `project_strategy3_display_name_gap.md`; (2) Capital.com emits a NEW
        dealId on broker-initiated closes (see
        `project_capital_com_dealid_mutation.md`) so the dealId guard that was
        protecting Strategy 3 masked the legitimate TP/SL close. Any position
        that cannot be matched by dealId / reference is now DEFERRED by the
        caller, and `CloseDetector` (activity-as-SoT, Step 4/5) handles the
        broker-initiated case deterministically via `/history/activity`.

        Exit price is taken from `closeLevel` when present; otherwise it is
        unknown and we fall back to `entry_price` so the DB column stays
        populated. The realized P&L is the authoritative figure.

        Returns (exit_price, pnl, close_reason) or (None, None, None).
        """

        def _finalize(txn, *, strategy: str) -> tuple[float | None, float | None, str | None]:
            pnl = txn.pl_value
            if pnl is None:
                return None, None, None
            exit_price = txn.close_level if txn.close_level is not None else entry_price
            if pnl > 0:
                reason = "TP"
            elif pnl < 0:
                reason = "SL"
            else:
                reason = "EXTERNAL"
            logger.info(
                f"[{epic}] Matched broker transaction via {strategy}: "
                f"exit={exit_price:.6f}, P&L=${pnl:.2f}, reason={reason} "
                f"(deal_id={txn.deal_id}, ref={txn.reference}, "
                f"instrument={txn.instrument_name})"
            )
            return exit_price, pnl, reason

        # Strategy 1: dealId (deterministic — current schema)
        if deal_id:
            for txn in transactions:
                if txn.deal_id and txn.deal_id == deal_id:
                    result = _finalize(txn, strategy="dealId")
                    if result[0] is not None:
                        return result

        # Strategy 2: reference (legacy schema fallback)
        ref_keys = {k for k in (deal_reference, deal_id) if k}
        if ref_keys:
            for txn in transactions:
                if txn.reference in ref_keys:
                    result = _finalize(txn, strategy="reference")
                    if result[0] is not None:
                        return result

        return None, None, None

    async def _detect_broker_closed(self, current_positions: list[dict]) -> None:
        """Three-tier close detection.

        Tier 1 (primary):   Transaction History API match → write REAL data.
        Tier 2 (deferred):  no match → keep in _pending_close_detections,
                            retry on next loop iteration.
        Tier 3 (timeout):   10min without match → write UNRECONCILED record.

        Close-detection v2 (activity-as-source-of-truth) runs in SHADOW MODE
        when CLOSE_DETECTION_V2_ENABLED is set. v1 remains authoritative; v2
        outcomes are logged + emitted as Prometheus counters so disagreements
        surface before the flag is promoted to primary.
        """
        if self.execution_engine.mode == ExecutionMode.PAPER:
            return

        self._broker_closed_deals = set()
        now = datetime.now(UTC)
        _settings = get_settings()
        timeout_sec = _settings.close_reconciliation_timeout_seconds
        v2_enabled = bool(getattr(_settings, "close_detection_v2_enabled", False))

        current_deals = {p.get("deal_id") for p in current_positions if p.get("deal_id")}

        # Snapshot BEFORE any mutation so the shadow detector sees the same
        # "previous" view that v1 saw at the start of this tick.
        previous_snapshot: dict[str, dict] = dict(self._previous_positions) if v2_enabled else {}

        if not self._previous_positions and not self._pending_close_detections:
            self._previous_positions = {
                p.get("deal_id"): p for p in current_positions if p.get("deal_id")
            }
            return

        newly_disappeared = [
            (did, ppos)
            for did, ppos in self._previous_positions.items()
            if did not in current_deals and did not in self._pending_close_detections
        ]
        retry_pending = list(self._pending_close_detections.items())

        if not newly_disappeared and not retry_pending:
            self._previous_positions = {
                p.get("deal_id"): p for p in current_positions if p.get("deal_id")
            }
            return

        transactions = await self._fetch_recent_transactions()
        if transactions:
            logger.info(
                f"Fetched {len(transactions)} recent transactions for "
                f"{len(newly_disappeared)} new + {len(retry_pending)} pending"
            )

        # v1 per-deal outcome trace; fed to shadow comparator at end.
        v1_outcomes: dict[str, str] = {}

        # Bridge deal_reference from DB for all disappeared ids
        deal_ref_map: dict[str, str | None] = {}
        disappeared_ids = [did for did, _ in newly_disappeared] + [did for did, _ in retry_pending]
        if disappeared_ids and self._db_session_factory is not None:
            try:
                from sqlalchemy import select

                from src.database.models import Position as DBPosition

                async with self._db_session_factory() as session:
                    stmt = select(DBPosition.deal_id, DBPosition.deal_reference).where(
                        DBPosition.deal_id.in_(disappeared_ids)
                    )
                    rows = (await session.execute(stmt)).all()
                    deal_ref_map = {row.deal_id: row.deal_reference for row in rows}
            except Exception as e:
                logger.warning(f"deal_reference DB lookup failed: {e}")

        # Build a stable-key index for the live broker positions. Capital.com
        # rotates the dealId between order-confirmation and /positions (last
        # hex nibble +1), so a string-equality check on deal_id misses
        # positions that are in fact still open. Pair by
        # ``(epic, direction, entry_price ± 0.1%)`` — the triple broker
        # *never* mutates for the lifetime of a position.
        def _position_is_live(pending: PendingClose) -> bool:
            for p in current_positions:
                if p.get("epic") != pending.epic:
                    continue
                pdir = p.get("direction")
                pdir_str = getattr(pdir, "value", pdir)
                if (str(pdir_str) or "").upper() != (pending.direction or "").upper():
                    continue
                try:
                    level = float(p.get("level") or 0)
                except (TypeError, ValueError):
                    continue
                if pending.entry_price <= 0:
                    continue
                if abs(level - pending.entry_price) / pending.entry_price < 0.001:
                    return True
            return False

        # ============ Retry previously-deferred closes ============
        for deal_id, pending in retry_pending:
            # Safety net: if the broker still has this position alive
            # (match via deal_id OR via the stable
            # (epic, direction, entry_price) triple), remove it from the
            # pending queue. reinject_orphans pushed it in on a transient
            # empty list_positions() at startup or a dealId-rotation hit,
            # and without this net a spurious UNRECONCILED alert would
            # fire 10 minutes later on a live position.
            if deal_id in current_deals or _position_is_live(pending):
                logger.warning(
                    f"[{pending.epic}] Pending close {deal_id} still "
                    f"live at broker (matched by deal_id or "
                    f"epic+direction+entry_price) — removing from "
                    f"pending queue (false-positive orphan from state "
                    f"recovery or broker dealId rotation)"
                )
                del self._pending_close_detections[deal_id]
                continue

            pending.retry_count += 1
            deal_ref = pending.deal_reference or deal_ref_map.get(deal_id)
            txn_exit, txn_pnl, txn_reason = self._match_transaction(
                transactions,
                deal_id,
                deal_ref,
                pending.epic,
                pending.entry_price,
            )
            if txn_exit is not None and txn_pnl is not None:
                logger.info(
                    f"[{pending.epic}] Reconciled after {pending.retry_count} retries: "
                    f"exit={txn_exit:.6f}, P&L=${txn_pnl:.2f}"
                )
                await self._finalize_close(
                    deal_id=deal_id,
                    epic=pending.epic,
                    direction=pending.direction,
                    size=pending.size,
                    entry_price=pending.entry_price,
                    prev_pos=pending.prev_pos,
                    exit_price=txn_exit,
                    pnl=txn_pnl,
                    close_reason=txn_reason or "EXTERNAL",
                    metric_path="primary",
                    retry_count=pending.retry_count,
                )
                del self._pending_close_detections[deal_id]
                v1_outcomes[deal_id] = "primary"
                continue

            age = (now - pending.first_seen).total_seconds()
            if age > timeout_sec:
                await self._emit_unreconciled_close(pending)
                del self._pending_close_detections[deal_id]
                v1_outcomes[deal_id] = "unreconciled"
            else:
                v1_outcomes[deal_id] = "deferred"

        # ============ Newly-disappeared positions ============
        for deal_id, prev_pos in newly_disappeared:
            epic = prev_pos.get("epic", "UNKNOWN")
            direction = prev_pos.get("direction", "BUY")
            size = prev_pos.get("size", 0)
            entry_price = prev_pos.get("level", 0)
            deal_reference = prev_pos.get("deal_reference") or deal_ref_map.get(deal_id)

            txn_exit, txn_pnl, txn_reason = self._match_transaction(
                transactions,
                deal_id,
                deal_reference,
                epic,
                entry_price,
            )

            if txn_exit is not None and txn_pnl is not None:
                await self._finalize_close(
                    deal_id=deal_id,
                    epic=epic,
                    direction=direction,
                    size=size,
                    entry_price=entry_price,
                    prev_pos=prev_pos,
                    exit_price=txn_exit,
                    pnl=txn_pnl,
                    close_reason=txn_reason or "EXTERNAL",
                    metric_path="primary",
                    retry_count=0,
                )
                v1_outcomes[deal_id] = "primary"
            else:
                logger.warning(
                    f"[{epic}] Close detected but no broker transaction match for "
                    f"{deal_id} — deferring (timeout {timeout_sec}s)"
                )
                try:
                    from src.monitoring.metrics import MetricsCollector

                    MetricsCollector.record_close_detection(path="deferred", epic=epic)
                except Exception:
                    pass
                self._pending_close_detections[deal_id] = PendingClose(
                    deal_id=deal_id,
                    deal_reference=deal_reference,
                    epic=epic,
                    direction=direction,
                    size=float(size or 0),
                    entry_price=float(entry_price or 0),
                    prev_pos=prev_pos,
                    first_seen=now,
                    retry_count=0,
                )
                v1_outcomes[deal_id] = "deferred"

        # Shadow v2 — non-authoritative, observe + compare only.
        if v2_enabled:
            await self._run_shadow_close_detection(
                previous_snapshot=previous_snapshot,
                current_positions=current_positions,
                transactions=transactions,
                v1_outcomes=v1_outcomes,
            )

        self._previous_positions = {
            p.get("deal_id"): p for p in current_positions if p.get("deal_id")
        }

    def _get_close_detector(self):
        """Lazy CloseDetector constructor for shadow-mode comparisons.

        Returns ``None`` when we cannot build one (e.g. no broker injected in
        unit-test paths). Instantiation is deferred so tests and PAPER mode
        never pay the FX / FRED construction cost.
        """
        if self._close_detector is not None:
            return self._close_detector
        if self.broker is None:
            return None
        try:
            from src.broker.fx import FxConverter
            from src.trading.close_detector import CloseDetector

            self._close_detector = CloseDetector(
                broker=self.broker,
                fx_converter=FxConverter(),
                account_currency=self._account_currency,
            )
            logger.info(
                f"[v2-shadow] CloseDetector initialized (account_currency="
                f"{self._account_currency!r})"
            )
        except Exception as e:
            logger.warning(f"[v2-shadow] CloseDetector init failed: {e!r}")
            self._close_detector = None
        return self._close_detector

    async def _run_shadow_close_detection(
        self,
        *,
        previous_snapshot: dict[str, dict],
        current_positions: list[dict],
        transactions: list,
        v1_outcomes: dict[str, str],
    ) -> None:
        """Invoke v2 CloseDetector in shadow mode and record disagreements.

        Non-authoritative: nothing here writes to the DB, the pending queue,
        alerts, or trade history. Purpose is purely observability during the
        24h shadow window described in the plan.
        """
        detector = self._get_close_detector()
        if detector is None:
            return

        try:
            from src.monitoring.metrics import MetricsCollector
            from src.trading.close_detector import Deferred, Reconciled, Unreconciled
        except Exception as e:
            logger.warning(f"[v2-shadow] import failed: {e!r}")
            return

        try:
            outcomes = await detector.detect(
                previous=previous_snapshot,
                current=current_positions,
                transactions=transactions,
            )
        except Exception as e:
            logger.warning(f"[v2-shadow] detect raised: {e!r}")
            for deal_id, prev_pos in previous_snapshot.items():
                if deal_id in v1_outcomes:
                    MetricsCollector.record_close_detection_v2_shadow(
                        outcome="error", epic=prev_pos.get("epic", "UNKNOWN")
                    )
            return

        for outcome in outcomes:
            deal_id = outcome.deal_id
            prev_pos = previous_snapshot.get(deal_id, {})
            epic = prev_pos.get("epic", "UNKNOWN")
            if isinstance(outcome, Reconciled):
                v2_label = "reconciled"
                logger.info(
                    f"[v2-shadow] {deal_id} → Reconciled "
                    f"(close_dealid={outcome.close_dealid}, pnl=${outcome.pnl:.2f}, "
                    f"exit={outcome.exit_price:.6f}, reason={outcome.close_reason})"
                )
            elif isinstance(outcome, Deferred):
                v2_label = "deferred"
                logger.info(f"[v2-shadow] {deal_id} → Deferred (reason={outcome.reason})")
            elif isinstance(outcome, Unreconciled):
                v2_label = "unreconciled"
                logger.warning(f"[v2-shadow] {deal_id} → Unreconciled (reason={outcome.reason})")
            else:  # pragma: no cover — defensive
                v2_label = "error"

            MetricsCollector.record_close_detection_v2_shadow(outcome=v2_label, epic=epic)

            v1_label = v1_outcomes.get(deal_id, "unobserved")
            # v1 uses "primary" for successful reconciliation; v2 calls that
            # "reconciled". Normalize so the disagreement metric only fires on
            # genuine decision divergence.
            v1_equivalent = "reconciled" if v1_label == "primary" else v1_label
            if v1_equivalent != v2_label:
                MetricsCollector.record_close_shadow_disagreement(
                    v1_path=v1_label, v2_outcome=v2_label, epic=epic
                )
                logger.warning(
                    f"[v2-shadow] DISAGREEMENT {deal_id} epic={epic} "
                    f"v1={v1_label} v2={v2_label}"
                )

    async def _finalize_close(
        self,
        *,
        deal_id: str,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        prev_pos: dict,
        exit_price: float,
        pnl: float,
        close_reason: str,
        metric_path: str = "primary",
        retry_count: int = 0,
    ) -> None:
        """Persist a matched close (Tier 1 success, immediate or via retry)."""
        logger.warning(
            f"[{epic}] Position {deal_id} closed by broker "
            f"(reason={close_reason}, exit={exit_price:.6f}, P&L=${pnl:.2f}, "
            f"retry={retry_count})"
        )

        try:
            from src.monitoring.metrics import MetricsCollector

            MetricsCollector.record_close_detection(
                path=metric_path, epic=epic, retry_count=retry_count
            )
        except Exception:
            pass

        self._broker_closed_deals.add(deal_id)
        self._on_position_closed(deal_id, pnl, epic=epic, close_reason=close_reason)

        try:
            fresh_equity = await self._fetch_equity()
            self.risk_manager.update_equity(fresh_equity)
            logger.info(f"[{epic}] Equity refreshed after close: ${fresh_equity:,.2f}")
        except Exception as eq_err:
            logger.debug(f"Post-close equity refresh failed: {eq_err}")

        await self._persist_position_close(
            deal_id=deal_id,
            epic=epic,
            direction=direction,
            size=size,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            close_reason=close_reason,
            opened_at=prev_pos.get("opened_at"),
        )

        if deal_id in self.trailing_stop_manager.tracked_positions:
            self.trailing_stop_manager.unregister_position(deal_id)

        try:
            from src.api.websocket import ws_manager

            await ws_manager.broadcast(
                "trades",
                {
                    "type": "trade_closed",
                    "deal_id": deal_id,
                    "epic": epic,
                    "direction": direction,
                    "pnl": round(pnl, 2),
                    "close_reason": close_reason,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as e:
            logger.debug(f"WS broadcast trade_closed failed: {e}")

        if self._log_source in ("demo_trading", "live_trading"):
            try:
                from src.monitoring.alerting.alert_manager import get_alert_manager
                from src.utils.config import get_settings

                if getattr(get_settings(), "alerts_enabled", False):
                    am = get_alert_manager()
                    await am.alert_trade_closed(
                        epic=epic,
                        direction=direction,
                        deal_id=deal_id,
                        exit_price=exit_price,
                        pnl=round(pnl, 2),
                        reason=close_reason,
                    )
            except Exception as alert_err:
                logger.warning(f"Trade close alert failed: {alert_err}")

    async def _emit_unreconciled_close(self, pending: "PendingClose") -> None:
        """Tier 3: persist a close we could not reconcile with broker data.

        pnl=NULL, close_reason='UNRECONCILED'. Downstream stats must skip it.
        """
        logger.error(
            f"[{pending.epic}] UNRECONCILED close after {pending.retry_count} "
            f"retries: deal_id={pending.deal_id}, prev_pos={pending.prev_pos}"
        )

        try:
            from src.monitoring.metrics import MetricsCollector

            MetricsCollector.record_close_detection(
                path="unreconciled", epic=pending.epic, retry_count=pending.retry_count
            )
        except Exception:
            pass

        self._broker_closed_deals.add(pending.deal_id)
        exit_price = float(pending.prev_pos.get("level") or pending.entry_price)

        await self._persist_position_close(
            deal_id=pending.deal_id,
            epic=pending.epic,
            direction=pending.direction,
            size=pending.size,
            entry_price=pending.entry_price,
            exit_price=exit_price,
            pnl=None,
            close_reason="UNRECONCILED",
            opened_at=pending.prev_pos.get("opened_at"),
        )

        if pending.deal_id in self.trailing_stop_manager.tracked_positions:
            self.trailing_stop_manager.unregister_position(pending.deal_id)

        try:
            from src.api.websocket import ws_manager

            await ws_manager.broadcast(
                "trades",
                {
                    "type": "trade_closed",
                    "deal_id": pending.deal_id,
                    "epic": pending.epic,
                    "direction": pending.direction,
                    "pnl": None,
                    "close_reason": "UNRECONCILED",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as e:
            logger.debug(f"WS broadcast unreconciled close failed: {e}")

        if self._log_source in ("demo_trading", "live_trading"):
            try:
                from src.monitoring.alerting.alert_manager import get_alert_manager
                from src.monitoring.alerting.schemas import Alert, AlertSeverity, AlertType
                from src.utils.config import get_settings

                if getattr(get_settings(), "alerts_enabled", False):
                    am = get_alert_manager()
                    alert = Alert(
                        alert_type=AlertType.POSITION_STUCK,
                        severity=AlertSeverity.WARNING,
                        title=f"UNRECONCILED CLOSE: {pending.epic}",
                        message=(
                            f"Position {pending.deal_id} closed by broker but P&L not confirmed "
                            f"after {pending.retry_count} retries. "
                            f"Run: python scripts/reconcile_position.py "
                            f"--deal-id {pending.deal_id}"
                        ),
                        epic=pending.epic,
                        details={
                            "direction": pending.direction,
                            "deal_id": pending.deal_id,
                            "exit_price": exit_price,
                            "retry_count": pending.retry_count,
                        },
                    )
                    await am.send_alert(alert)
            except Exception as alert_err:
                logger.warning(f"Unreconciled close alert failed: {alert_err}")

    async def _persist_trailing_stop_state(self, deal_id: str) -> None:
        """
        Persist trailing stop state for a specific position.

        Args:
            deal_id: Position deal identifier
        """
        if self._db_session_factory is None:
            return  # No database available, skip persistence

        try:
            from decimal import Decimal

            from src.broker.models import Direction
            from src.database.repositories import TrailingStopRepository

            state = self.trailing_stop_manager.get_state(deal_id)
            if state is None:
                return  # Position not tracked

            async with self._db_session_factory() as session:
                repo = TrailingStopRepository(session)

                await repo.upsert(
                    deal_id=deal_id,
                    epic=state.epic,
                    direction=Direction(state.direction),
                    entry_price=Decimal(str(state.entry_price)),
                    current_stop=Decimal(str(state.current_stop)),
                    phase=state.phase,
                    tp1_level=Decimal(str(state.tp1_level)) if state.tp1_level else None,
                    tp2_level=Decimal(str(state.tp2_level)) if state.tp2_level else None,
                    highest_price=(
                        Decimal(str(state.highest_price)) if state.highest_price else None
                    ),
                    lowest_price=Decimal(str(state.lowest_price)) if state.lowest_price else None,
                )
                await session.commit()
                logger.debug(f"Persisted trailing stop state for {deal_id}")
        except Exception as e:
            logger.warning(f"Trailing stop persistence failed for {deal_id}: {e}")

    def start(self) -> None:
        """Start the paper trading loop."""
        if self._running:
            logger.warning("Paper trading loop is already running")
            return

        # Reset heartbeat so the 30s timeout doesn't trip on first iteration
        # (CircuitBreakerManager may have been created minutes/hours ago at startup)
        self.risk_manager.circuit_breakers.heartbeat()

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="paper_trading_loop")
        self._task.add_done_callback(self._on_task_done)
        logger.info(
            f"Paper trading loop started (check every {self.interval_seconds}s, "
            f"epics={self.epics})"
        )

    def stop(self) -> None:
        """Stop the paper trading loop."""
        if not self._running:
            logger.warning("Paper trading loop is not running")
            return

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Paper trading loop stopped")

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Callback when the loop task finishes — auto-restart on crash."""
        if task.cancelled():
            self._running = False
            return
        exc = task.exception()
        if exc:
            logger.error(f"🚨 Paper trading loop crashed: {exc}")
            # Auto-restart after 30 seconds
            logger.info("🔄 Auto-restarting paper trading loop in 30 seconds...")
            self._running = False
            try:
                loop = asyncio.get_event_loop()
                loop.call_later(30.0, self._auto_restart)
            except RuntimeError:
                logger.error("Cannot auto-restart: no event loop available")

    def _auto_restart(self) -> None:
        """Auto-restart the trading loop after a crash."""
        if self._running:
            return  # Already running (manual restart happened)
        logger.info("🔄 Auto-restarting paper trading loop now...")
        self.start()

    async def _run_loop(self) -> None:
        """Main loop: check for new candles at fixed intervals."""
        consecutive_errors = 0
        max_consecutive_errors = 10

        # Run first iteration immediately (process all epics regardless)
        try:
            await self._run_iteration(force=True)
            consecutive_errors = 0
        except Exception as e:
            self._error_count += 1
            consecutive_errors += 1
            logger.error(f"First iteration failed: {e}")

        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await self._run_iteration(force=False)
                consecutive_errors = 0  # Reset on success
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                self._error_count += 1
                logger.error(
                    f"Paper trading iteration error ({consecutive_errors}/{max_consecutive_errors}): {e}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"🚨 {max_consecutive_errors} consecutive errors — "
                        f"stopping loop for auto-restart"
                    )
                    raise  # Let _on_task_done handle restart
                # Exponential backoff: 30s, 60s, 120s, ... max 5min
                backoff = min(30 * (2 ** (consecutive_errors - 1)), 300)
                logger.info(f"Waiting {backoff}s before next attempt...")
                await asyncio.sleep(backoff)

    def _has_new_candle(self, epic: str) -> bool:
        """Check if there's a new candle since last processed."""
        if self.data_access is None:
            return True  # No data access → always run (legacy behavior)

        try:
            latest = self.data_access.get_latest_price(epic, timeframe=self._candle_resolution)
            if latest is None:
                return False

            candle_ts = latest.get("timestamp")
            if candle_ts is None:
                return False

            last_ts = self._last_candle_ts.get(epic)

            if last_ts is None or candle_ts > last_ts:
                self._last_candle_ts[epic] = candle_ts
                return True
            return False
        except Exception as e:
            logger.debug(f"[{epic}] Candle check failed: {e}")
            return True  # On error, run anyway to avoid missing signals

    async def _is_market_open(self, epic: str) -> tuple[bool, str | None]:
        """Check if market is open via cached broker market details."""
        if not self.broker:
            return True, None  # No broker → assume open (PAPER mode)

        now = _time.monotonic()
        cached_ts = self._market_cache_ts.get(epic, 0)
        if epic in self._market_info_cache and (now - cached_ts) < self._market_cache_ttl:
            info = self._market_info_cache[epic]
        else:
            try:
                info = await asyncio.wait_for(self.broker.get_market_details(epic), timeout=10.0)
                self._market_info_cache[epic] = info
                self._market_cache_ts[epic] = now
                # Sync dedicated min deal size cache
                min_val = info.get("dealingRules", {}).get("minDealSize", {}).get("value")
                if min_val is not None:
                    self._min_deal_size_cache[epic] = float(min_val)
            except Exception as e:
                logger.debug(f"[{epic}] Market info fetch failed: {e}")
                return True, None  # Graceful: if fetch fails, try anyway

        status = info.get("snapshot", {}).get("marketStatus", "TRADEABLE")
        if status != "TRADEABLE":
            return False, f"Mercato {epic} chiuso (status: {status})"
        return True, None

    def _get_min_deal_size(self, epic: str) -> float | None:
        """
        Get minDealSize with fallback chain:
        1. _market_info_cache (fresh data from _is_market_open each iteration)
        2. _min_deal_size_cache (seeded at startup from DB/prefetch)
        3. None (validation skipped, broker will reject if too small)
        """
        # Priority 1: Fresh data from _is_market_open() cache
        info = self._market_info_cache.get(epic)
        if info:
            dealing_rules = info.get("dealingRules", {})
            min_deal = dealing_rules.get("minDealSize", {})
            value = min_deal.get("value")
            if value is not None:
                return float(value)

        # Priority 2: Pre-fetched / DB-loaded cache
        if epic in self._min_deal_size_cache:
            return self._min_deal_size_cache[epic]

        return None

    def seed_min_deal_sizes(self, sizes: dict[str, float]) -> None:
        """Seed the min deal size cache with pre-fetched or DB-loaded data."""
        self._min_deal_size_cache.update(sizes)
        logger.info(f"Seeded min deal size cache with {len(sizes)} entries")

    async def _run_iteration(self, *, force: bool = False) -> None:
        """
        Check for new candles and run predictions where needed.

        Args:
            force: If True, process all epics regardless of candle status.
        """
        self._check_count += 1

        # Phase 8: circuit breaker heartbeat (resets timeout counter)
        self.risk_manager.circuit_breakers.heartbeat()

        # Daily reset: reset daily P&L tracking and daily circuit breakers at midnight UTC
        today_utc = datetime.now(UTC).strftime("%Y-%m-%d")
        if not hasattr(self, "_last_daily_reset_date") or self._last_daily_reset_date != today_utc:
            self.risk_manager.drawdown_monitor.reset_daily()
            self.risk_manager.circuit_breakers.reset_daily()
            self._last_daily_reset_date = today_utc
            logger.info(f"Daily reset triggered for {today_utc}")

        # Fetch positions once per iteration (avoid N+1)
        try:
            current_positions = await asyncio.wait_for(self.get_positions_async(), timeout=10.0)
        except (TimeoutError, Exception) as e:
            logger.warning(f"Position fetch timed out/failed ({e}), using local cache")
            current_positions = self.get_paper_positions()

        # Detect positions closed by broker (SL/TP hit on Capital.com side)
        await self._detect_broker_closed(current_positions)

        # Phase 8: update trailing stops for open positions
        await self._update_trailing_stops(current_positions)

        # CRITICAL: Check and auto-close positions with violated stop losses
        await self._check_stop_losses(current_positions)

        # Refresh spread blocks hourly — unblock epics whose spread improved
        await self._refresh_spread_blocks()
        await self._refresh_correlation_regime()
        self._init_regime_gate()

        open_epics = {p.get("epic") for p in current_positions}

        # Early exit: skip signal generation if already at max open positions
        max_positions = self.risk_manager.circuit_breakers.config.max_open_positions
        if len(current_positions) >= max_positions:
            logger.debug(
                f"Check #{self._check_count}: at max positions "
                f"({len(current_positions)}/{max_positions}), skipping signal generation"
            )
            return

        # Asset rotation disabled: ScalpScore + session filter handle selection
        # self._refresh_active_assets()
        self._active_assets = None

        epics_to_process = []
        for epic in self.epics:
            if not self.prediction_service.has_model_for(epic):
                continue
            if epic in open_epics:
                continue  # Already has open position
            if force or self._has_new_candle(epic):
                epics_to_process.append(epic)

        if not epics_to_process:
            logger.debug(f"Check #{self._check_count}: no new candles, skipping")
            return

        self._iteration_count += 1
        self._last_run = datetime.now(UTC)
        logger.info(
            f"Paper trading iteration #{self._iteration_count} "
            f"(check #{self._check_count}, epics: {epics_to_process})"
        )

        # Fetch SIL data once per iteration (cached internally by each client)
        if _settings.sil_enabled and self._sil_clients_initialized:
            try:
                self._sil_data = await self._fetch_sil_data()
            except Exception as e:
                logger.warning(f"[SIL] Data fetch failed, using defaults: {e}")
                self._sil_data = SILData()

        for epic in epics_to_process:
            try:
                # Refresh heartbeat per-epic so the 30s timeout measures
                # "loop alive" not "total iteration duration" (21 epics can exceed 30s)
                self.risk_manager.circuit_breakers.heartbeat()
                await self._process_epic(epic, current_positions)
            except Exception as e:
                self._error_count += 1
                logger.error(f"Error processing {epic} (total errors: {self._error_count}): {e}")

        # Phase 14: persist risk state after iteration
        await self._persist_risk_state()

    async def _fetch_m1_bars(self, epic: str):
        """
        Fetch today's M1 bars from broker for ORB+FVG strategy.

        Returns a Polars DataFrame with columns: timestamp, open, high, low, close.
        Returns None if broker is unavailable or no data.
        """
        if not self.broker:
            return None

        try:
            from zoneinfo import ZoneInfo

            import polars as pl

            from src.broker.models import Resolution

            _ET = ZoneInfo("America/New_York")
            _BROKER_TZ = ZoneInfo("Europe/Berlin")

            now_utc = datetime.now(UTC)
            now_et = now_utc.astimezone(_ET)

            # Only fetch during NYSE session (09:25 - 16:05 ET)
            if now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 25):
                return None
            if now_et.hour >= 17:
                return None

            # Fetch from 09:25 ET today to now
            from_dt = now_et.replace(hour=9, minute=25, second=0, microsecond=0)
            from_utc = from_dt.astimezone(UTC).replace(tzinfo=None)
            to_utc = now_utc.replace(tzinfo=None)

            candles = await asyncio.wait_for(
                self.broker.get_historical_prices(
                    epic=epic,
                    resolution=Resolution.MINUTE,
                    from_date=from_utc,
                    to_date=to_utc,
                    max_candles=1000,
                ),
                timeout=15.0,
            )

            if not candles:
                return None

            # Convert to DataFrame, handling CET timestamps from broker
            rows = []
            for c in candles:
                ts = c.timestamp
                if ts.tzinfo is None:
                    # Broker returns CET/CEST — convert to UTC
                    aware = ts.replace(tzinfo=_BROKER_TZ)
                    ts = aware.astimezone(UTC).replace(tzinfo=None)
                rows.append(
                    {
                        "timestamp": ts,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                    }
                )

            if not rows:
                return None

            df = pl.DataFrame(rows).sort("timestamp")
            logger.debug(f"[{epic}] Fetched {len(df)} M1 bars for ORB+FVG")
            return df

        except TimeoutError:
            logger.warning(f"[{epic}] M1 bar fetch timed out")
            return None
        except Exception as e:
            logger.warning(f"[{epic}] M1 bar fetch failed: {e}")
            return None

    async def _fetch_equity(self) -> float:
        """Get current equity. DEMO/LIVE: from broker. PAPER: from risk manager."""
        if self.broker and self.execution_engine.mode != ExecutionMode.PAPER:
            try:
                accounts = await asyncio.wait_for(self.broker.get_accounts(), timeout=10.0)
                if accounts:
                    acc = accounts[0]
                    # Capital.com: 'deposit' is the funded amount, 'balance' can be 0
                    base = acc.deposit or acc.available or acc.balance
                    return base + acc.profit_loss
            except Exception as e:
                logger.warning(f"Broker equity fetch failed, using local: {e}")
        return self.risk_manager.drawdown_monitor.state.current_equity

    async def _process_epic(self, epic: str, open_positions: list[dict]) -> None:
        """Run the full pipeline for a single epic."""
        # Asset rotation check
        if self._active_assets is not None and epic not in self._active_assets:
            return  # Skip non-active assets

        # Per-asset circuit breaker (5 consecutive losses)
        if self._per_asset_losses.get(epic, 0) >= 5:
            logger.debug(f"[{epic}] Per-asset CB: 5 consecutive losses, skipping")
            return

        # Rolling asset exclusion (14-day Sharpe < threshold)
        _pe_settings = get_settings()
        if _pe_settings.scalp_asset_exclusion_enabled:
            excluded, sharpe = self._asset_tracker.is_excluded(epic)
            if excluded:
                return

        # Step 0: Market hours check (DEMO/LIVE only)
        is_open, closed_reason = await self._is_market_open(epic)
        if not is_open:
            signal_info = {
                "epic": epic,
                "direction": "HOLD",
                "confidence": 0.0,
                "entry_price": 0.0,
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "market_closed",
                "rejection_reason": closed_reason,
            }
            self._last_signals[epic] = signal_info
            self._signal_history.appendleft(signal_info)
            logger.info(f"[{epic}] {closed_reason}")
            return

        # Step 0b: Economic Calendar gate (SIL)
        if self._calendar_gate is not None:
            try:
                is_blackout, blackout_reason = await self._calendar_gate.is_blackout(epic)
                if is_blackout:
                    signal_info = {
                        "epic": epic,
                        "direction": "HOLD",
                        "confidence": 0.0,
                        "entry_price": 0.0,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "status": "calendar_blackout",
                        "rejection_reason": blackout_reason,
                    }
                    self._last_signals[epic] = signal_info
                    self._signal_history.appendleft(signal_info)
                    logger.info(f"[{epic}] {blackout_reason}")
                    return
            except Exception as e:
                logger.debug(f"[{epic}] Calendar gate error (non-blocking): {e}")

        # Step 1: ML Prediction
        prediction = self.prediction_service.predict(
            epic,
            timeframe=self._candle_resolution,
            sil_data=self._sil_data if self._sil_clients_initialized else None,
        )
        if prediction is None:
            logger.debug(f"[{epic}] No prediction generated")
            return

        logger.info(
            f"[{epic}] Prediction: {prediction.signal_name} "
            f"(confidence={prediction.confidence:.3f})"
        )

        # Step 2: Get market data
        market_data = self.prediction_service.get_market_data(
            epic, timeframe=self._candle_resolution
        )
        if market_data is None:
            logger.warning(f"[{epic}] No market data available")
            return

        # Step 2a: Inject SIL composite score for ScalpScore sentiment vote
        if self._sil_data and self._sil_clients_initialized:
            _fg = self._sil_data.fear_greed
            _fred = self._sil_data.fred

            # FIX: Only compute composite if we have REAL data (not just defaults).
            # Default SILData has fear_greed.value=50, bullish_ratio=0.5, etc.
            # which produces a fake neutral composite (~0.375) masking real sentiment.
            _has_real_data = (
                _fg.value != 50.0  # default is 50
                or _fred.real_yield_10y is not None
                or self._sil_data.cot.net_position_normalized != 0.0
            )

            if _has_real_data:
                from src.features.sil_features import _compute_composite

                _real_yield = _fred.real_yield_10y if _fred.real_yield_10y is not None else 0.0
                market_data["sil_composite_score"] = _compute_composite(
                    fear_greed_value=_fg.normalized,
                    gold_bullish_yield=1.0 if _real_yield < -1.0 else 0.0,
                    alpha_bullish=self._sil_data.alpha_vantage.bullish_ratio,
                    cot_net_norm=self._sil_data.cot.net_position_normalized,
                    social_bullish=self._sil_data.social.combined_bullish_ratio,
                )
            else:
                market_data["sil_composite_score"] = 0.0  # No real data → neutral

        # Step 2b: Fetch M1 bars for ORB+FVG epics
        if epic in self.strategy_manager.orb_fvg_epics:
            m1_bars = await self._fetch_m1_bars(epic)
            if m1_bars is not None:
                market_data["m1_bars"] = m1_bars

        # Log market state with regime info (Step 7: regime detection)
        regime = market_data.get("regime", "unknown")
        adx = market_data.get("adx", 0)
        rsi = market_data.get("rsi", 0)
        logger.info(f"[{epic}] Market state: regime={regime}, ADX={adx:.1f}, RSI={rsi:.1f}")

        # Track regime distribution
        if epic not in self._regime_counts:
            self._regime_counts[epic] = {}
        self._regime_counts[epic][regime] = self._regime_counts[epic].get(regime, 0) + 1

        # Step 3: Strategy -> TradingSignal
        signal = self.strategy_manager.process_prediction(prediction, epic, market_data)
        self._signal_count += 1
        # Meta-label features: logged with each signal for future ML training
        _ml_htf = market_data.get("htf_bias")
        _ml_features = {
            "ml_confluence": round(signal.confidence * 6, 1),
            "ml_utc_hour": datetime.now(UTC).hour,
            "ml_adx": round(float(market_data.get("adx", 0)), 1),
            "ml_rsi": round(float(market_data.get("rsi", 50)), 1),
            "ml_atr": round(float(market_data.get("atr", 0)), 5),
            "ml_htf_bias": 1 if _ml_htf == "bullish" else (-1 if _ml_htf == "bearish" else 0),
            "ml_regime": market_data.get("regime", "unknown"),
        }

        # Compute SL cooldown info for this epic (before signal_info)
        _sl_count = self._get_recent_sl_count(epic)
        _sl_cooldown_info = None
        if _sl_count > 0:
            _sl_cooldown_info = {
                "sl_count": _sl_count,
                "max_strikes": self._epic_sl_max_strikes,
                "penalty": self.get_epic_sl_penalty(epic),
                "blocked": _sl_count >= self._epic_sl_max_strikes,
                "window_hours": self._epic_sl_window_hours,
            }

        signal_info = {
            "epic": epic,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "predicted",
            "strategy_name": signal.strategy_name,
            "sl_cooldown": _sl_cooldown_info,
            **_ml_features,
        }
        self._last_signals[epic] = signal_info
        self._signal_history.appendleft(signal_info)

        # --- Audit trail: build features dict from signal metadata ---
        audit_features = None
        if self._signal_repo_factory and signal.metadata:
            try:
                audit_features = {
                    "version": 1,
                    "rejection_reason": None,
                    "votes": signal.metadata.get("votes"),
                    "gates": signal.metadata.get("gates"),
                    "ml": signal.metadata.get("ml"),
                    "risk": None,
                    "market_snapshot": signal.metadata.get("market_snapshot"),
                }
            except Exception:
                logger.warning(f"[{epic}] Failed to build audit features")

        # Map direction to SignalType for structured logging
        _dir_map = {"BUY": SignalType.LONG, "SELL": SignalType.SHORT, "HOLD": SignalType.HOLD}
        _signal_type = _dir_map.get(signal.direction.value, SignalType.HOLD)

        # Epic SL cooldown: apply progressive penalty based on recent SL hits
        sl_penalty = self.get_epic_sl_penalty(epic)
        if sl_penalty < 1.0 and signal.direction.value != "HOLD":
            if sl_penalty <= 0.0:
                sl_count = self._get_recent_sl_count(epic)
                logger.info(
                    f"[{epic}] EPIC COOLDOWN: {sl_count} SL in "
                    f"{self._epic_sl_window_hours:.0f}h → HOLD"
                )
                signal = signal.model_copy(
                    update={
                        "direction": SignalDirection.HOLD,
                        "confidence": 0.0,
                    }
                )
                signal_info["status"] = "hold"
                signal_info["rejection_reason"] = (
                    f"Epic cooldown: {sl_count} SL in {self._epic_sl_window_hours:.0f}h"
                )
            else:
                pre_penalty = signal.confidence
                signal = signal.model_copy(
                    update={
                        "confidence": signal.confidence * sl_penalty,
                    }
                )
                logger.info(
                    f"[{epic}] SL penalty {sl_penalty:.2f}x: "
                    f"conf {pre_penalty:.3f} → {signal.confidence:.3f}"
                )

        logger.info(
            f"[{epic}] Signal: {signal.direction.value} "
            f"@ {signal.entry_price:.2f} "
            f"(confidence={signal.confidence:.3f})"
        )

        # Record signal metric
        MetricsCollector.record_signal(
            epic=epic,
            direction=signal.direction.value,
            strategy=signal.strategy_name or "unknown",
            confidence=signal.confidence,
        )

        if signal.direction.value == "HOLD":
            signal_info["status"] = "hold"
            # Persist HOLD as REJECTED audit
            if audit_features is not None:
                audit_features["rejection_reason"] = "Insufficient confluence (HOLD)"
                await self._persist_signal_audit(
                    epic=epic,
                    direction="HOLD",
                    confidence=signal.confidence,
                    entry_price=signal.entry_price,
                    stop_loss=signal.suggested_stop,
                    take_profit=signal.suggested_tp,
                    status="REJECTED",
                    features=audit_features,
                )
            # Log HOLD signal
            try:
                await get_trade_logger().log_signal(
                    epic=epic,
                    direction=_signal_type,
                    confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.HOLD,
                    source=self._log_source,
                )
            except Exception:
                pass
            logger.info(f"[{epic}] HOLD signal, skipping execution")
            return

        # Duplicate protection: open_epics check already done in _run_iteration
        # (line 975: `if epic in open_epics: continue`).
        # No time-based dedup — if a position was closed and the signal is still
        # valid, the system should be free to re-enter immediately.

        # Step 3b: Spread filter — reject if spread cost > MAX_SPREAD_PCT of TP distance
        _spread_settings = get_settings()
        if self.broker and _spread_settings.max_spread_pct > 0:
            try:
                market_details = await self.broker.get_market_details(epic)
                snapshot = market_details.get("snapshot", {})
                bid = snapshot.get("bid", 0)
                offer = snapshot.get("offer", 0)
                if bid and offer and signal.entry_price > 0:
                    spread = offer - bid
                    # Estimate TP distance from ATR
                    _tp_rr = (
                        _spread_settings.scalp_tp_risk_reward
                        if _spread_settings.scalp_mode_enabled
                        else 2.5
                    )
                    tp_distance = market_data["atr"] * _tp_rr
                    if tp_distance > 0:
                        spread_ratio = spread / tp_distance
                        if spread_ratio > _spread_settings.max_spread_pct:
                            reason = (
                                f"Spread too high: {spread:.6f} = "
                                f"{spread_ratio:.1%} of TP distance "
                                f"(limit {_spread_settings.max_spread_pct:.0%})"
                            )
                            logger.warning(f"[{epic}] {reason}")
                            signal_info["status"] = "rejected"
                            signal_info["rejection_reason"] = reason
                            # Track blocked epics for API
                            self._spread_blocked_epics[epic] = {
                                "spread": round(spread, 8),
                                "spread_pct": round(spread_ratio * 100, 1),
                                "limit_pct": round(_spread_settings.max_spread_pct * 100, 1),
                                "since": datetime.now(UTC).isoformat(),
                            }
                            return
                        else:
                            # Clear block if spread came back to normal
                            self._spread_blocked_epics.pop(epic, None)
            except Exception as e:
                logger.debug(f"[{epic}] Spread check failed (non-blocking): {e}")

        # Step 3d: Regime Gate — block if HMM confidence low or feature drift detected
        if self._regime_gate is not None:
            try:
                recent_bars = market_data.get("recent_bars")
                if recent_bars is not None and len(recent_bars) >= 20:
                    gate_decision = self._regime_gate.check(
                        recent_bars,
                        feature_columns=self._regime_gate_feature_cols[:30],
                    )
                    if not gate_decision.approved:
                        logger.info(f"[{epic}] Regime gate BLOCKED: {gate_decision.reason}")
                        signal_info["status"] = "rejected"
                        signal_info["rejection_reason"] = f"Regime gate: {gate_decision.reason}"
                        return
            except Exception as e:
                logger.debug(f"[{epic}] Regime gate check failed (non-blocking): {e}")

        # Step 4: Risk check (Phase 8: pass trade_history for Kelly sizing)
        equity = await self._fetch_equity()
        self.risk_manager.update_equity(equity)
        risk_result = self.risk_manager.check_trade(
            signal=signal,
            equity=equity,
            atr=market_data["atr"],
            open_positions=open_positions,
            trade_history=self._trade_history or None,
        )

        if not risk_result.approved:
            signal_info["status"] = "rejected"
            signal_info["rejection_reason"] = risk_result.rejection_reason
            logger.info(f"[{epic}] Risk REJECTED: {risk_result.rejection_reason}")
            # Log rejected signal + risk event
            try:
                tl = get_trade_logger()
                await tl.log_signal(
                    epic=epic,
                    direction=_signal_type,
                    confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.REJECTED,
                    rejection_reason=risk_result.rejection_reason,
                    source=self._log_source,
                )
                # Detect circuit breaker vs other rejection types
                is_cb = bool(risk_result.circuit_breaker_details)
                _event_type = (
                    RiskEventType.CIRCUIT_BREAKER if is_cb else RiskEventType.POSITION_LIMIT
                )
                _cb_losses = None
                if is_cb:
                    _cb_losses = risk_result.circuit_breaker_details.get("consecutive_losses")
                await tl.log_risk_decision(
                    event_type=_event_type,
                    epic=epic,
                    description=risk_result.rejection_reason or "Risk check failed",
                    action="rejected_trade",
                    current_equity=equity,
                    open_positions=len(open_positions),
                    consecutive_losses=_cb_losses,
                    source=self._log_source,
                )
            except Exception as _log_err:
                logger.error(f"[{epic}] Failed to log risk decision: {_log_err}")

            # Persist REJECTED signal audit trail
            if audit_features is not None:
                audit_features["risk"] = risk_result.audit
                audit_features["rejection_reason"] = risk_result.rejection_reason
                await self._persist_signal_audit(
                    epic=epic,
                    direction=signal.direction.value,
                    confidence=signal.confidence,
                    entry_price=signal.entry_price,
                    stop_loss=signal.suggested_stop,
                    take_profit=signal.suggested_tp,
                    status="REJECTED",
                    features=audit_features,
                )

            return

        logger.info(
            f"[{epic}] Risk APPROVED: size={risk_result.position_size:.4f}, "
            f"SL={risk_result.stop_loss}, TP={risk_result.take_profit} "
            f"sizing={risk_result.sizing_method}"
        )

        # Step 4b: Validate against broker minDealSize (DEMO/LIVE only)
        # If size is close to minimum (>=80%), round up instead of rejecting
        min_deal_size = self._get_min_deal_size(epic)
        if min_deal_size is not None and risk_result.position_size < min_deal_size:
            # Always round up to broker minimum — risk already approved the trade,
            # the size difference is marginal and blocking it wastes valid signals.
            logger.info(
                f"[{epic}] Size {risk_result.position_size:.4f} rounded up "
                f"to min_deal_size {min_deal_size}"
            )
            risk_result.position_size = min_deal_size

        # Correlation regime adjustment: reduce size during panic
        if self._correlation_regime == "panic" and get_settings().correlation_regime_enabled:
            reduction = get_settings().correlation_regime_size_reduction
            original_size = risk_result.position_size
            risk_result.position_size *= 1.0 - reduction
            risk_result.adjustments.append(
                f"Correlation regime PANIC: size reduced by {reduction:.0%} "
                f"({original_size:.4f} -> {risk_result.position_size:.4f})"
            )
            logger.info(
                f"[{epic}] Correlation panic regime: size {original_size:.4f} "
                f"-> {risk_result.position_size:.4f}"
            )

        # Add approved risk audit data to features
        if audit_features is not None:
            audit_features["risk"] = risk_result.audit

        # HIGH-8 FIX: Refresh equity immediately before execution
        # to catch any changes since risk check (manual trades, other systems, etc.)
        final_equity = await self._fetch_equity()
        if abs(final_equity - equity) > equity * 0.01:  # >1% change
            logger.warning(
                f"[{epic}] Equity changed since risk check: "
                f"{equity:.2f} -> {final_equity:.2f} "
                f"({((final_equity - equity) / equity) * 100:+.2f}%)"
            )
            self.risk_manager.update_equity(final_equity)

        # Step 5: Execute (paper mode)
        exec_start = _time.monotonic()
        exec_result = await self.execution_engine.execute_signal(signal, risk_result)
        exec_duration = _time.monotonic() - exec_start

        if exec_result.success:
            self._trade_count += 1
            signal_info["status"] = "executed"
            logger.info(
                f"[{epic}] EXECUTED: deal_id={exec_result.deal_id}, "
                f"fill={exec_result.fill_price:.2f}"
            )
            MetricsCollector.record_trade_execution(
                epic=epic,
                direction=signal.direction.value,
                outcome="success",
                duration_seconds=exec_duration,
            )

            # Adjust strategy SL/TP for fill drift and round to broker precision.
            # The strategy (MR) already computed correct SL/TP with TP_MAX_ATR cap;
            # we only shift them proportionally if fill drifted from signal price.
            actual_entry = exec_result.fill_price or signal.entry_price
            from src.utils.price_rounding import round_price

            # Shift SL/TP by the fill drift (preserves strategy's R:R / ATR ratios)
            fill_drift = actual_entry - signal.entry_price
            new_sl = risk_result.stop_loss + fill_drift if risk_result.stop_loss else None
            new_tp = risk_result.take_profit + fill_drift if risk_result.take_profit else None

            # Round to broker tick precision (1 decimal for indices, etc.)
            new_sl = round_price(epic, new_sl)
            new_tp = round_price(epic, new_tp)

            _risk_dist = abs(actual_entry - new_sl) if new_sl else 0
            _reward_dist = abs(actual_entry - new_tp) if new_tp else 0
            _actual_rr = _reward_dist / _risk_dist if _risk_dist > 0 else 0
            logger.info(
                f"[{epic}] Post-fill SL/TP: fill={actual_entry} drift={fill_drift:.4f} "
                f"SL={new_sl} TP={new_tp} R:R={_actual_rr:.2f}"
            )
            risk_result.stop_loss = new_sl
            risk_result.take_profit = new_tp

            # Push the rounded MR levels to the broker (modify_stops on the
            # already-open position). Capital.com tends to accept narrower
            # stops on a modify than on a create.
            #
            # CRITICAL: Capital.com returns DIFFERENT dealIds for create vs list.
            # The exec_result.deal_id is from creation; modify requires the
            # list_positions() dealId. We look it up by epic with retries to
            # allow broker propagation.
            if exec_result.deal_id and new_sl and new_tp and self.broker:
                actual_deal_id = exec_result.deal_id
                for attempt_delay in (1.5, 2.5, 4.0):
                    try:
                        await asyncio.sleep(attempt_delay)
                        positions = await self.broker.list_positions()
                        for p in positions:
                            if p.epic == epic:
                                actual_deal_id = p.deal_id
                                break
                        if actual_deal_id != exec_result.deal_id:
                            logger.debug(
                                f"[{epic}] Resolved modify dealId: "
                                f"{exec_result.deal_id[:16]} -> {actual_deal_id[:16]}"
                            )
                            break
                    except Exception as e:
                        logger.debug(f"[{epic}] Position lookup attempt failed: {e}")
                        continue

                try:
                    update_result = await self.execution_engine.update_stops(
                        deal_id=actual_deal_id,
                        stop_level=new_sl,
                        profit_level=new_tp,
                    )
                    if update_result.success:
                        logger.info(
                            f"[{epic}] Broker SL/TP modified to MR values: "
                            f"SL={new_sl} TP={new_tp}"
                        )
                        # Re-read to capture any further broker adjustments
                        try:
                            actual_sl, actual_tp = await self._read_broker_stops(
                                actual_deal_id, epic
                            )
                            if actual_sl is not None:
                                exec_result.actual_stop_loss = actual_sl
                            if actual_tp is not None:
                                exec_result.actual_take_profit = actual_tp
                            if (
                                actual_sl
                                and actual_tp
                                and (actual_sl != new_sl or actual_tp != new_tp)
                            ):
                                logger.warning(
                                    f"[{epic}] Broker post-modify deviation: "
                                    f"sent SL={new_sl} TP={new_tp}, "
                                    f"broker has SL={actual_sl} TP={actual_tp}"
                                )
                        except Exception as e:
                            logger.debug(f"[{epic}] Could not re-read stops: {e}")
                    else:
                        # FULL error logging — this is the diagnostic data we need
                        logger.error(
                            f"[{epic}] BROKER REJECTED MODIFY: error={update_result.error} "
                            f"detail={update_result.error_detail} | "
                            f"sent SL={new_sl} TP={new_tp} fill={actual_entry} "
                            f"direction={signal.direction.value}"
                        )
                except Exception as e:
                    logger.warning(f"[{epic}] Exception modifying broker stops: {e}")

            # CRITICAL: Use the broker's ACTUAL SL/TP as authoritative source.
            # The broker may have adjusted our requested levels (min-distance
            # constraints, etc.). Trailing stop and DB must match what the
            # broker actually has, not what we asked for.
            _entry = exec_result.fill_price or signal.entry_price
            _requested_sl = risk_result.stop_loss
            _requested_tp = risk_result.take_profit
            _broker_sl = exec_result.actual_stop_loss
            _broker_tp = exec_result.actual_take_profit
            _sl = _broker_sl if _broker_sl is not None else _requested_sl
            _tp = _broker_tp if _broker_tp is not None else _requested_tp

            _sl_deviation = (_sl - _requested_sl) if (_sl and _requested_sl) else 0.0
            _tp_deviation = (_tp - _requested_tp) if (_tp and _requested_tp) else 0.0

            if _broker_sl is not None and abs(_sl_deviation) > 1e-6:
                logger.warning(
                    f"[{epic}] Broker adjusted SL: {_requested_sl:.4f} -> {_broker_sl:.4f} "
                    f"(deviation {_sl_deviation:+.4f})"
                )
            if _broker_tp is not None and abs(_tp_deviation) > 1e-6:
                logger.warning(
                    f"[{epic}] Broker adjusted TP: {_requested_tp:.4f} -> {_broker_tp:.4f} "
                    f"(deviation {_tp_deviation:+.4f})"
                )

            # Track deviation for API exposure
            if exec_result.deal_id:
                self._level_deviations[exec_result.deal_id] = {
                    "requested_sl": _requested_sl,
                    "requested_tp": _requested_tp,
                    "actual_sl": _sl,
                    "actual_tp": _tp,
                    "sl_deviation": round(_sl_deviation, 6),
                    "tp_deviation": round(_tp_deviation, 6),
                    "sl_deviation_pct": round(
                        (_sl_deviation / _entry * 100) if _entry > 0 else 0, 4
                    ),
                    "tp_deviation_pct": round(
                        (_tp_deviation / _entry * 100) if _entry > 0 else 0, 4
                    ),
                }

            # Phase 8: register position for trailing stop management.
            # _sl is the broker-confirmed SL (post-fill modify aligned to MR levels).
            if exec_result.deal_id:
                self.trailing_stop_manager.register_position(
                    deal_id=exec_result.deal_id,
                    epic=epic,
                    direction=signal.direction.value,
                    entry_price=actual_entry,
                    stop_loss=_sl,
                    atr=market_data["atr"],
                )
                # Phase 14: persist trailing stop state
                await self._persist_trailing_stop_state(exec_result.deal_id)

            # Sanity check: validate R:R is in a sane range (using broker values)
            if _sl and _tp and _entry > 0:
                _risk = abs(_entry - _sl)
                _reward = abs(_entry - _tp)
                _rr = _reward / _risk if _risk > 0 else 0
                _sl_dist_pct = _risk / _entry * 100
                if _rr < 0.5 or _rr > 5.0 or _sl_dist_pct < 0.05:
                    logger.warning(
                        f"[{epic}] SUSPICIOUS LEVELS: R:R={_rr:.2f}, "
                        f"SL_dist={_sl_dist_pct:.3f}%, "
                        f"entry={_entry:.4f} SL={_sl:.4f} TP={_tp:.4f} "
                        f"({signal.direction.value})"
                    )
                else:
                    logger.info(
                        f"[{epic}] Levels OK (broker confirmed): R:R={_rr:.2f}, "
                        f"SL_dist={_sl_dist_pct:.2f}%, "
                        f"entry={_entry:.4f} SL={_sl:.4f} TP={_tp:.4f}"
                    )

            # Persist position to database with broker-confirmed levels
            await self._persist_position_open(
                deal_id=exec_result.deal_id or "",
                epic=epic,
                direction=signal.direction.value,
                size=risk_result.position_size,
                entry_price=_entry,
                stop_loss=_sl,
                take_profit=_tp,
                deal_reference=exec_result.deal_reference,
            )

            # Log executed signal + execution
            try:
                tl = get_trade_logger()
                await tl.log_signal(
                    epic=epic,
                    direction=_signal_type,
                    confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.EXECUTED,
                    source=self._log_source,
                )
                await tl.log_execution(
                    epic=epic,
                    direction=signal.direction.value,
                    size=risk_result.position_size,
                    entry_price=exec_result.fill_price or signal.entry_price,
                    status=ExecutionStatus.EXECUTED,
                    deal_id=exec_result.deal_id,
                    stop_loss=_sl,
                    take_profit=_tp,
                    equity_at_entry=equity,
                    source=self._log_source,
                )
            except Exception:
                pass

            # Persist EXECUTED signal audit trail + link to position
            if audit_features is not None:
                signal_id = await self._persist_signal_audit(
                    epic=epic,
                    direction=signal.direction.value,
                    confidence=signal.confidence,
                    entry_price=exec_result.fill_price or signal.entry_price,
                    stop_loss=_sl,
                    take_profit=_tp,
                    status="EXECUTED",
                    features=audit_features,
                )
                # Link signal to position via deal_id
                if signal_id and exec_result.deal_id and self._signal_repo_factory:
                    try:
                        async with self._signal_repo_factory() as session:
                            from src.database.repositories.position_repository import (
                                PositionRepository,
                            )
                            from src.database.repositories.signal_repository import SignalRepository

                            pos_repo = PositionRepository(session)
                            position = await pos_repo.get_by_deal_id(exec_result.deal_id)
                            if position:
                                sig_repo = SignalRepository(session)
                                await sig_repo.mark_as_executed(signal_id, position.id)
                                await session.commit()
                    except Exception as e:
                        logger.warning(f"[{epic}] Signal-position link failed: {e}")

            # MANTIS-EVOLUTION: Run multi-agent analysis (non-blocking enrichment)
            if self._agents_enabled and self._orchestrator:
                try:
                    from src.agents.schemas import MarketContext

                    agent_ctx = MarketContext(
                        epic=epic,
                        current_price=signal.entry_price,
                        atr=market_data.get("atr", 1.0),
                        features=market_data,
                        regime=market_data.get("regime"),
                        open_positions=len(open_positions),
                        equity=equity,
                    )
                    agent_decision = await self._orchestrator.run(agent_ctx)
                    signal_info["agent_decision"] = {
                        "action": agent_decision.action,
                        "approved": agent_decision.approved,
                        "confidence": agent_decision.confidence,
                        "override_reason": agent_decision.override_reason,
                        "audit_trail": agent_decision.agent_audit_trail[:5],  # first 5 entries
                    }
                    logger.info(
                        f"[{epic}] Agent decision: {agent_decision.action} "
                        f"(approved={agent_decision.approved}, conf={agent_decision.confidence:.2f})"
                    )
                except Exception as e:
                    logger.debug(f"[{epic}] Agent enrichment failed: {e!r}")

        elif exec_result.error_detail and exec_result.error_detail.get("error_type") == "min_size":
            # Broker rejected for minimum size — retry with min_deal_size from broker
            broker_min = None
            try:
                info = await asyncio.wait_for(self.broker.get_market_details(epic), timeout=10.0)
                broker_min_raw = info.get("dealingRules", {}).get("minDealSize", {}).get("value")
                if broker_min_raw is not None:
                    broker_min = float(broker_min_raw)
                    self._min_deal_size_cache[epic] = broker_min
            except Exception:
                pass

            if broker_min is not None and broker_min > risk_result.position_size:
                logger.info(
                    f"[{epic}] Retrying with broker min_deal_size: "
                    f"{risk_result.position_size:.4f} -> {broker_min}"
                )
                risk_result.position_size = broker_min
                exec_result = await self.execution_engine.execute_signal(signal, risk_result)

            if exec_result.success:
                # Retry succeeded — fall through to success handling below
                self._trade_count += 1
                signal_info["status"] = "executed"
                logger.info(
                    f"[{epic}] EXECUTED (retry): deal_id={exec_result.deal_id}, "
                    f"fill={exec_result.fill_price:.2f}"
                )
                # Adjust strategy SL/TP for fill drift (retry path)
                actual_entry = exec_result.fill_price or signal.entry_price
                fill_drift = actual_entry - signal.entry_price
                from src.utils.price_rounding import round_price as _rp

                _adj_sl = risk_result.stop_loss + fill_drift if risk_result.stop_loss else None
                _adj_tp = risk_result.take_profit + fill_drift if risk_result.take_profit else None
                _adj_sl = _rp(epic, _adj_sl)
                _adj_tp = _rp(epic, _adj_tp)
                _sl_valid = (
                    _validate_sl_side(signal.direction.value, actual_entry, _adj_sl)
                    if _adj_sl
                    else False
                )
                _tp_valid = (
                    _validate_tp_side(signal.direction.value, actual_entry, _adj_tp)
                    if _adj_tp
                    else False
                )
                if _sl_valid and _tp_valid:
                    risk_result.stop_loss = _adj_sl
                    risk_result.take_profit = _adj_tp
                # Use broker-confirmed values when available
                _r_broker_sl = exec_result.actual_stop_loss
                _r_broker_tp = exec_result.actual_take_profit
                _r_sl = _r_broker_sl if _r_broker_sl is not None else risk_result.stop_loss
                _r_tp = _r_broker_tp if _r_broker_tp is not None else risk_result.take_profit
                if _r_broker_sl is not None and _r_broker_sl != risk_result.stop_loss:
                    logger.warning(
                        f"[{epic}] Broker adjusted SL (retry path): "
                        f"{risk_result.stop_loss:.4f} -> {_r_broker_sl:.4f}"
                    )
                if _r_broker_tp is not None and _r_broker_tp != risk_result.take_profit:
                    logger.warning(
                        f"[{epic}] Broker adjusted TP (retry path): "
                        f"{risk_result.take_profit:.4f} -> {_r_broker_tp:.4f}"
                    )
                if exec_result.deal_id:
                    self.trailing_stop_manager.register_position(
                        deal_id=exec_result.deal_id,
                        epic=epic,
                        direction=signal.direction.value,
                        entry_price=actual_entry,
                        stop_loss=_r_sl,
                        atr=market_data["atr"],
                    )
                    await self._persist_trailing_stop_state(exec_result.deal_id)
                await self._persist_position_open(
                    deal_id=exec_result.deal_id or "",
                    epic=epic,
                    direction=signal.direction.value,
                    size=risk_result.position_size,
                    entry_price=actual_entry,
                    stop_loss=_r_sl,
                    take_profit=_r_tp,
                    deal_reference=exec_result.deal_reference,
                )
            else:
                signal_info["status"] = "exec_failed"
                signal_info["rejection_reason"] = exec_result.error
                logger.warning(f"[{epic}] Execution retry also failed: {exec_result.error}")
        else:
            signal_info["status"] = "exec_failed"
            signal_info["rejection_reason"] = exec_result.error
            if exec_result.error_detail:
                signal_info["error_detail"] = exec_result.error_detail
            logger.warning(f"[{epic}] Execution failed: {exec_result.error}")
            MetricsCollector.record_trade_execution(
                epic=epic,
                direction=signal.direction.value,
                outcome="failed",
                duration_seconds=exec_duration,
            )
            # Log failed execution
            try:
                tl = get_trade_logger()
                await tl.log_signal(
                    epic=epic,
                    direction=_signal_type,
                    confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.EXEC_FAILED,
                    rejection_reason=exec_result.error,
                    source=self._log_source,
                )
                await tl.log_execution(
                    epic=epic,
                    direction=signal.direction.value,
                    size=risk_result.position_size,
                    entry_price=signal.entry_price,
                    status=ExecutionStatus.EXEC_FAILED,
                    error_message=exec_result.error,
                    source=self._log_source,
                )
            except Exception:
                pass

            # Persist EXEC_FAILED signal audit trail
            if audit_features is not None:
                audit_features["rejection_reason"] = exec_result.error
                await self._persist_signal_audit(
                    epic=epic,
                    direction=signal.direction.value,
                    confidence=signal.confidence,
                    entry_price=signal.entry_price,
                    stop_loss=risk_result.stop_loss,
                    take_profit=risk_result.take_profit,
                    status="REJECTED",
                    features=audit_features,
                )

    async def _persist_signal_audit(
        self,
        epic: str,
        direction: str,
        confidence: float,
        entry_price: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        status: str,
        features: dict,
    ) -> int | None:
        """Best-effort persist signal audit to DB. Returns signal ID or None."""
        if not self._signal_repo_factory:
            logger.debug(f"[{epic}] Signal audit skipped: no repo factory")
            return None
        try:
            logger.debug(f"[{epic}] Persisting {status} signal audit...")
            async with self._signal_repo_factory() as session:
                from src.database.repositories.signal_repository import SignalRepository

                repo = SignalRepository(session)
                signal_id = await repo.create_from_audit(
                    epic=epic,
                    direction=direction,
                    confidence=confidence,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    status=status,
                    features=features,
                )
                await session.commit()
                logger.info(f"[{epic}] Signal audit persisted (id={signal_id}, status={status})")
                return signal_id
        except Exception as e:
            logger.warning(f"[{epic}] Signal audit persist failed: {e!r}")
            return None

    async def _update_trailing_stops(self, current_positions: list[dict]) -> None:
        """
        Update trailing stops for all tracked positions.
        Called once per iteration to advance stop phases and trigger partial closes.
        """
        tracked = self.trailing_stop_manager.tracked_positions
        if not tracked:
            return

        # Build position lookup for current prices
        pos_by_id = {p.get("deal_id"): p for p in current_positions}

        for deal_id in list(tracked):
            position = pos_by_id.get(deal_id)
            if position is None:
                # Position was closed externally
                self.trailing_stop_manager.unregister_position(deal_id)
                continue

            # Get CURRENT market price (NOT position.level which is the entry price).
            # Prefer broker bid/offer; fall back to market_data current_price.
            epic = position.get("epic", "")
            direction = position.get("direction", "BUY")
            current_price: float = 0.0
            atr = None
            try:
                md = self.prediction_service.get_market_data(epic)
                if md:
                    atr = md.get("atr")
                    # For BUY positions: exit at bid; for SELL: exit at offer
                    current_price = float(md.get("current_price", 0))
            except Exception:
                pass

            # Fall back to broker market details for live bid/offer
            if current_price <= 0 and self.broker:
                try:
                    details = await self.broker.get_market_details(epic)
                    snap = details.get("snapshot", {}) if isinstance(details, dict) else {}
                    bid = snap.get("bid", 0)
                    offer = snap.get("offer", 0)
                    if bid and offer:
                        current_price = float(bid) if direction == "BUY" else float(offer)
                except Exception as e:
                    logger.debug(f"[{epic}] Market details fetch failed: {e}")

            if current_price <= 0:
                continue

            state_before = self.trailing_stop_manager.get_state(deal_id)
            phase_before = (
                TrailingPhase(state_before.phase) if state_before else TrailingPhase.INITIAL
            )

            new_stop, phase = self.trailing_stop_manager.update_price(
                deal_id=deal_id,
                current_price=current_price,
                current_atr=atr,
            )

            # Update broker/paper stop if changed
            if new_stop is not None:
                try:
                    await self.execution_engine.update_stops(deal_id, new_stop)
                    # Phase 14: persist updated trailing stop state
                    await self._persist_trailing_stop_state(deal_id)
                except Exception as e:
                    logger.debug(f"[{epic}] Stop update failed: {e}")

            # Phase 8: partial close at TP1 (INITIAL → BREAKEVEN transition)
            if phase == TrailingPhase.BREAKEVEN and phase_before == TrailingPhase.INITIAL:
                try:
                    result = await self.execution_engine.partial_close(deal_id, 0.5, "TP1_HIT")
                    if result.success:
                        logger.info(f"[{epic}] TP1 hit: closed 50% of position")
                        # In DEMO/LIVE mode, partial_close returns a NEW deal_id
                        # (close + reopen). Update trailing stop tracking if changed.
                        new_deal_id = result.deal_id
                        if new_deal_id and new_deal_id != deal_id:
                            state = self.trailing_stop_manager.get_state(deal_id)
                            if state:
                                self.trailing_stop_manager.unregister_position(deal_id)
                                self.trailing_stop_manager.register_position(
                                    deal_id=new_deal_id,
                                    epic=state.epic,
                                    direction=state.direction,
                                    entry_price=state.entry_price,
                                    stop_loss=state.current_stop,
                                    atr=None,
                                )
                                logger.info(
                                    f"[{epic}] Trailing stop migrated: "
                                    f"{deal_id} -> {new_deal_id}"
                                )
                except Exception as e:
                    logger.warning(f"[{epic}] TP1 partial close failed: {e}")

    async def _check_stop_losses(self, current_positions: list[dict]) -> None:
        """
        CRITICAL: Check if any open position has violated its stop loss OR take profit
        OR exceeded the maximum hold time (time-based stop).
        Auto-close positions where:
          - Time stop: position held longer than max_hold_hours
          - SL violated: price <= SL (longs) or price >= SL (shorts)
          - TP hit: price >= TP (longs) or price <= TP (shorts)

        This is essential for locally-managed risk when broker doesn't have SL/TP set.
        """
        if not current_positions:
            return

        _loop_settings = get_settings()
        # When MR is the primary strategy, use the MR-specific (shorter) time-stop.
        # MR positions stale after ~1*OU half-life (~24h on 4h bars) -> close them.
        if _loop_settings.mr_primary_enabled:
            max_hold_hours = _loop_settings.mr_max_hold_hours
        else:
            max_hold_hours = _loop_settings.scalp_max_hold_hours
        now_utc = datetime.now(UTC)

        for position in current_positions:
            deal_id = position.get("deal_id")
            epic = position.get("epic", "")
            direction = position.get("direction", "")
            stop_level = position.get("stop_level")
            profit_level = position.get("profit_level")

            # Skip positions already closed by _detect_broker_closed in this iteration
            broker_closed = getattr(self, "_broker_closed_deals", set())
            if deal_id and deal_id in broker_closed:
                logger.debug(
                    f"[{epic}] Skipping SL/TP check for {deal_id} — "
                    f"already closed by broker detection"
                )
                continue

            # --- Time-based stop: close stale positions ---
            # Skip if market is closed — can't close, and retrying every 15min
            # just spams errors (e.g. weekends for stocks/indices).
            market_status = position.get("market_status", "TRADEABLE")
            if market_status != "TRADEABLE":
                continue

            opened_at_str = position.get("opened_at")
            if opened_at_str and max_hold_hours < 9000:
                try:
                    opened_at = datetime.fromisoformat(str(opened_at_str))
                    if opened_at.tzinfo is None:
                        opened_at = opened_at.replace(tzinfo=UTC)
                    age_hours = (now_utc - opened_at).total_seconds() / 3600
                    if age_hours >= max_hold_hours:
                        logger.warning(
                            f"⏰ [{epic}] TIME STOP: position {deal_id} held "
                            f"{age_hours:.1f}h >= {max_hold_hours}h limit"
                        )
                        try:
                            result = await self.execution_engine.close_position(
                                deal_id=deal_id,
                                reason="TIME_STOP",
                            )
                            if result.success:
                                # Close-detection v2 (Step 7): do NOT compute
                                # synthetic P&L or persist here. Position will
                                # disappear from broker.list_positions on the
                                # next tick; _detect_broker_closed enqueues it
                                # and CloseDetector reconciles with the real
                                # broker TRADE row + FX.
                                logger.info(
                                    f"[{epic}] Time stop close submitted — awaiting "
                                    f"broker reconciliation (held {age_hours:.1f}h)"
                                )
                            continue  # Skip SL/TP checks for this position
                        except Exception as e:
                            logger.warning(f"[{epic}] Time stop close failed: {e}")
                except (ValueError, TypeError) as e:
                    logger.debug(f"[{epic}] Could not parse opened_at '{opened_at_str}': {e}")

            # Skip if no stop loss AND no take profit set
            if (stop_level is None or stop_level <= 0) and (
                profit_level is None or profit_level <= 0
            ):
                continue

            # Get current market price
            try:
                latest = self.data_access.get_latest_price(epic, timeframe="1h")
                if latest is None:
                    continue

                current_price = latest.get("close", 0)
                if current_price <= 0:
                    continue

                # Check if stop loss violated
                stop_violated = False
                entry_price = position.get("level") or position.get("entry_price", 0)
                if stop_level is not None and stop_level > 0:
                    # Sanity check: SL must be on correct side of entry
                    sl_sane = True
                    if entry_price and entry_price > 0:
                        if direction == "BUY" and stop_level >= entry_price:
                            sl_sane = False
                            logger.warning(
                                f"[{epic}] Ignoring invalid SL={stop_level:.5f} "
                                f">= entry={entry_price:.5f} for LONG (stale data?)"
                            )
                        elif direction == "SELL" and stop_level <= entry_price:
                            sl_sane = False
                            logger.warning(
                                f"[{epic}] Ignoring invalid SL={stop_level:.5f} "
                                f"<= entry={entry_price:.5f} for SHORT (stale data?)"
                            )
                    if sl_sane and direction == "BUY" and current_price <= stop_level:
                        stop_violated = True
                        logger.warning(
                            f"🚨 [{epic}] STOP LOSS VIOLATED! "
                            f"Price {current_price:.5f} <= SL {stop_level:.5f} (LONG)"
                        )
                    elif sl_sane and direction == "SELL" and current_price >= stop_level:
                        stop_violated = True
                        logger.warning(
                            f"🚨 [{epic}] STOP LOSS VIOLATED! "
                            f"Price {current_price:.5f} >= SL {stop_level:.5f} (SHORT)"
                        )

                # Check if take profit hit
                tp_hit = False
                if not stop_violated and profit_level is not None and profit_level > 0:
                    if direction == "BUY" and current_price >= profit_level:
                        tp_hit = True
                        logger.info(
                            f"🎯 [{epic}] TAKE PROFIT HIT! "
                            f"Price {current_price:.5f} >= TP {profit_level:.5f} (LONG)"
                        )
                    elif direction == "SELL" and current_price <= profit_level:
                        tp_hit = True
                        logger.info(
                            f"🎯 [{epic}] TAKE PROFIT HIT! "
                            f"Price {current_price:.5f} <= TP {profit_level:.5f} (SHORT)"
                        )

                # Auto-close position if SL violated or TP hit
                if stop_violated or tp_hit:
                    close_reason = "STOP_LOSS_HIT" if stop_violated else "TAKE_PROFIT_HIT"
                    reason_label = "SL" if stop_violated else "TP"
                    try:
                        logger.info(
                            f"[{epic}] Auto-closing position {deal_id} due to {close_reason}"
                        )

                        result = await self.execution_engine.close_position(
                            deal_id=deal_id,
                            reason=close_reason,
                        )

                        if result.success:
                            # Close-detection v2 (Step 7): no synthetic P&L
                            # here. Position disappears from broker on the
                            # next tick; CloseDetector reconciles real P&L
                            # from /history/transactions + FX. _on_position_closed
                            # + _persist_position_close + ws broadcast all fire
                            # from _finalize_close once reconciled.
                            logger.info(
                                f"[{epic}] Position close submitted at "
                                f"{reason_label} — awaiting broker reconciliation "
                                f"(trigger price {current_price:.5f})"
                            )
                            status = "sl_hit" if stop_violated else "tp_hit"
                            self._signal_history.append(
                                {
                                    "timestamp": datetime.now(UTC).isoformat(),
                                    "epic": epic,
                                    "direction": direction,
                                    "confidence": 0.0,
                                    "status": status,
                                    "reason": f"{reason_label} hit at {current_price:.5f}",
                                    "deal_id": deal_id,
                                    "pnl": None,  # pending reconciliation
                                }
                            )
                        else:
                            logger.error(
                                f"❌ [{epic}] Failed to close position at {reason_label}: {result.error}"
                            )

                    except Exception as e:
                        logger.error(f"❌ [{epic}] Error closing position at {reason_label}: {e}")

            except Exception as e:
                logger.debug(f"[{epic}] Risk level check failed: {e}")

    def _on_position_closed(
        self, deal_id: str, pnl: float | None, epic: str = "", close_reason: str = ""
    ) -> None:
        """
        Handle position close events for Phase 8 modules.
        Records trade result for circuit breakers, equity curve, Kelly history,
        per-asset circuit breaker, and epic SL cooldown tracker.
        """
        if pnl is None:
            logger.debug(
                f"[{epic}] _on_position_closed called with pnl=None "
                f"(UNRECONCILED) — skipping Kelly/CB/equity-filter updates"
            )
            return

        # Circuit breaker: track consecutive wins/losses
        self.risk_manager.circuit_breakers.record_trade_result(is_win=(pnl > 0))

        # Equity curve filter: record equity point
        equity = self.risk_manager.drawdown_monitor.state.current_equity
        self.risk_manager.equity_curve_filter.record_trade_close(equity)

        # Kelly: add to trade history (deque auto-discards oldest when maxlen=200 reached)
        self._trade_history.append({"pnl": pnl})

        # Epic SL cooldown: track SL hits per epic
        if close_reason == "SL" and epic:
            now = datetime.now(UTC)
            self._epic_sl_hits.setdefault(epic, []).append(now)
            recent = self._get_recent_sl_count(epic)
            if recent >= self._epic_sl_max_strikes:
                logger.warning(
                    f"[{epic}] EPIC COOLDOWN: {recent} SL hits in "
                    f"{self._epic_sl_window_hours}h — blocking further trades"
                )
                # Fire Telegram alert
                asyncio.ensure_future(self._alert_epic_cooldown(epic, recent))

        # Per-asset circuit breaker: track consecutive losses
        if epic:
            self._record_per_asset_result(epic, is_win=(pnl > 0))
            # Rolling asset performance tracker (Sharpe-based exclusion)
            self._asset_tracker.record_trade(epic, pnl)

        # Trailing stop: unregister
        self.trailing_stop_manager.unregister_position(deal_id)
        # Clean up level deviation tracking for this deal
        self._level_deviations.pop(deal_id, None)

    def _get_recent_sl_count(self, epic: str) -> int:
        """Count SL hits for an epic within the cooldown window."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=self._epic_sl_window_hours)
        hits = self._epic_sl_hits.get(epic, [])
        # Prune old entries
        recent = [t for t in hits if t > cutoff]
        self._epic_sl_hits[epic] = recent
        return len(recent)

    def get_epic_sl_penalty(self, epic: str) -> float:
        """Get confidence penalty for an epic based on recent SL hits.

        Returns multiplier: 1.0 (no penalty), 0.70 (1 SL), 0.40 (2 SL), 0.0 (3+ SL = blocked).
        """
        count = self._get_recent_sl_count(epic)
        if count >= self._epic_sl_max_strikes:
            return 0.0
        return {0: 1.0, 1: 0.70, 2: 0.40}.get(count, 0.0)

    def get_epic_sl_summary(self) -> dict[str, int]:
        """Get summary of recent SL hits per epic (for Telegram status)."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=self._epic_sl_window_hours)
        result = {}
        for epic, hits in self._epic_sl_hits.items():
            recent = [t for t in hits if t > cutoff]
            if recent:
                result[epic] = len(recent)
        return result

    async def _alert_epic_cooldown(self, epic: str, sl_count: int):
        """Fire Telegram alert when an epic enters cooldown."""
        try:
            from src.monitoring.alerting.alert_manager import get_alert_manager
            from src.monitoring.alerting.schemas import Alert, AlertSeverity, AlertType

            alert = Alert(
                alert_type=AlertType.CIRCUIT_BREAKER,
                severity=AlertSeverity.WARNING,
                title=f"Epic Cooldown: {epic}",
                message=(
                    f"{epic} bloccato dopo {sl_count} SL hit "
                    f"in {self._epic_sl_window_hours:.0f}h. "
                    f"Nessuna nuova trade fino al reset del cooldown."
                ),
                epic=epic,
                details={
                    "reason": "epic_sl_cooldown",
                    "sl_count": sl_count,
                    "window_hours": self._epic_sl_window_hours,
                },
            )
            am = get_alert_manager()
            await am.send_alert(alert)
        except Exception as e:
            logger.debug(f"Epic cooldown alert failed: {e}")

        # Phase 14: persist risk state after position close (skip if no event loop)
        try:
            asyncio.create_task(self._persist_risk_state())
        except RuntimeError:
            pass  # No event loop (called from tests)

    def _refresh_active_assets(self) -> None:
        """Refresh asset rotation weekly."""
        import time

        now = time.monotonic()
        if self._active_assets is not None and (now - self._asset_rotation_ts) < 7 * 24 * 3600:
            return  # Refresh weekly

        try:
            from src.data.data_access import DataAccessLayer
            from src.data.storage import ParquetStorageManager
            from src.trading.asset_rotation import compute_momentum_scores, select_active_assets

            storage = ParquetStorageManager()
            data_access = DataAccessLayer(storage=storage)
            scores = compute_momentum_scores(data_access)

            if scores:
                selected = select_active_assets(scores)
                self._active_assets = set(selected)
                self._asset_rotation_ts = now
                logger.info(f"Asset rotation: {len(selected)} active assets: {selected}")
            else:
                self._active_assets = None  # Fallback to all
        except Exception as e:
            logger.warning(f"Asset rotation failed: {e}")
            self._active_assets = None

    def _record_per_asset_result(self, epic: str, is_win: bool) -> None:
        """Track consecutive losses per asset for per-asset circuit breaker."""
        if is_win:
            self._per_asset_losses[epic] = 0
        else:
            self._per_asset_losses[epic] = self._per_asset_losses.get(epic, 0) + 1

    def get_status(self) -> dict:
        """Get current status of the trading loop (defensive copies, sync)."""
        positions = self.get_paper_positions()
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)

        # Phase 8: circuit breaker and trailing stop info
        cb_tripped = self.risk_manager.circuit_breakers.tripped_breakers
        trailing_tracked = self.trailing_stop_manager.tracked_positions
        eq_below_sma = self.risk_manager.equity_curve_filter.is_below_sma

        return {
            "running": self._running,
            "execution_mode": self.execution_engine.mode.value,
            "interval_seconds": self.interval_seconds,
            "epics": list(self.epics),
            "iteration_count": self._iteration_count,
            "check_count": self._check_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "signal_count": self._signal_count,
            "trade_count": self._trade_count,
            "error_count": self._error_count,
            "open_positions": len(positions),
            "total_unrealized_pnl": total_pnl,
            "last_signals": dict(self._last_signals),
            "models_loaded": self.prediction_service.get_loaded_models(),
            "last_candle_timestamps": {
                epic: ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                for epic, ts in self._last_candle_ts.items()
            },
            "circuit_breakers_tripped": cb_tripped,
            "trailing_stops_tracked": len(trailing_tracked),
            "equity_curve_below_sma": eq_below_sma,
            "kelly_trade_history_size": len(self._trade_history),
            "kelly_stats": self._get_kelly_stats(),
            "regime_distribution": dict(self._regime_counts),
            "min_deal_sizes_cached": len(self._min_deal_size_cache),
            "active_assets": len(self._active_assets) if self._active_assets else len(self.epics),
            "per_asset_losses": {k: v for k, v in self._per_asset_losses.items() if v > 0},
            "spread_blocked_epics": self._spread_blocked_epics,
            "correlation_regime": self._correlation_regime,
            "regime_gate": self._regime_gate.get_stats() if self._regime_gate else None,
            "epic_sl_cooldowns": self.get_epic_sl_summary(),
            "sil": {
                "enabled": _settings.sil_enabled,
                "clients_initialized": self._sil_clients_initialized,
                "calendar_gate_enabled": (
                    _settings.sil_calendar_gate_enabled if _settings.sil_enabled else False
                ),
                "fetch_errors": self._sil_data.fetch_errors if self._sil_data else [],
                "fear_greed_value": self._sil_data.fear_greed.value if self._sil_data else None,
                "composite_score": None,  # Populated from features
            },
            "agents": {
                "enabled": self._agents_enabled,
                "orchestrator_active": self._orchestrator is not None,
                "vision_enabled": _settings.vision_enabled,
                "drl_enabled": _settings.drl_enabled,
            },
        }

    def _get_kelly_stats(self) -> dict | None:
        """Compute Kelly stats for API response."""
        history = list(self._trade_history)
        if not history:
            return None
        if self.risk_manager.kelly_sizer is None:
            return None
        wins = [t["pnl"] for t in history if t["pnl"] > 0]
        losses = [t["pnl"] for t in history if t["pnl"] < 0]
        min_trades = self.risk_manager.kelly_sizer.min_trades
        stats = self.risk_manager.kelly_sizer.compute_stats(history)
        result: dict = {
            "total_trades": len(history),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / max(1, len(wins) + len(losses)),
            "total_pnl": round(sum(t["pnl"] for t in history), 2),
            "min_required": min_trades,
            "active": stats is not None,
            "method": "kelly" if stats else "fixed_fractional",
        }
        if stats:
            result["avg_win"] = round(stats.avg_win, 2)
            result["avg_loss"] = round(stats.avg_loss, 2)
            result["kelly_fraction"] = round(stats.kelly_fraction, 4)
            result["half_kelly"] = round(stats.half_kelly, 4)
        return result

    async def get_status_async(self) -> dict:
        """Get status with live position data (async, works for all modes)."""
        status = self.get_status()
        positions = await self.get_positions_async()
        status["open_positions"] = len(positions)
        status["total_unrealized_pnl"] = sum(p.get("unrealized_pnl", 0) for p in positions)
        return status
