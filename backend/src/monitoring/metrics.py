"""
Prometheus metrics for MANTIS AI.
Custom business metrics for trading, risk, and system monitoring.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ===== System Info =====
mantis_info = Info("mantis", "MANTIS AI system information")

# ===== Trading Metrics =====
mantis_open_positions_count = Gauge(
    "mantis_open_positions_count",
    "Number of open trading positions",
    ["epic", "direction"],
)

mantis_account_equity = Gauge(
    "mantis_account_equity",
    "Current account equity",
    ["mode"],  # PAPER, DEMO, LIVE
)

mantis_daily_pnl = Gauge(
    "mantis_daily_pnl",
    "Daily profit/loss",
    ["mode"],
)

mantis_total_pnl = Gauge(
    "mantis_total_pnl",
    "Total profit/loss since inception",
    ["mode"],
)

mantis_trades_executed_total = Counter(
    "mantis_trades_executed_total",
    "Total number of trades executed",
    ["epic", "direction", "outcome"],  # outcome: success, rejected, failed
)

mantis_trade_execution_duration_seconds = Histogram(
    "mantis_trade_execution_duration_seconds",
    "Trade execution latency in seconds",
    ["epic"],
)

# ===== Signal Metrics =====
mantis_signals_generated_total = Counter(
    "mantis_signals_generated_total",
    "Total trading signals generated",
    ["epic", "direction", "strategy"],
)

mantis_signal_confidence = Histogram(
    "mantis_signal_confidence",
    "Trading signal confidence scores",
    ["epic"],
    buckets=[0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0],
)

# ===== Risk Metrics =====
mantis_drawdown_pct = Gauge(
    "mantis_drawdown_pct",
    "Current drawdown percentage",
    ["type"],  # daily, total
)

mantis_circuit_breaker_trips_total = Counter(
    "mantis_circuit_breaker_trips_total",
    "Total circuit breaker activations",
    ["epic", "reason"],
)

mantis_risk_limit_breaches_total = Counter(
    "mantis_risk_limit_breaches_total",
    "Total risk limit breaches",
    ["limit_type"],  # position_size, max_positions, drawdown
)

mantis_consecutive_losses = Gauge(
    "mantis_consecutive_losses",
    "Current consecutive loss count",
    ["epic"],
)

# ===== ML Model Metrics =====
mantis_model_prediction_total = Counter(
    "mantis_model_prediction_total",
    "Total ML model predictions",
    ["epic", "model_type", "predicted_class"],
)

mantis_model_confidence = Histogram(
    "mantis_model_confidence",
    "ML model prediction confidence",
    ["epic", "model_type"],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

mantis_model_inference_duration_seconds = Histogram(
    "mantis_model_inference_duration_seconds",
    "ML model inference time in seconds",
    ["epic", "model_type"],
)

# ===== Database Metrics =====
mantis_db_query_duration_seconds = Histogram(
    "mantis_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],  # select, insert, update, delete
)

mantis_db_connection_pool_size = Gauge(
    "mantis_db_connection_pool_size",
    "Database connection pool size",
    ["state"],  # active, idle
)

# ===== Broker API Metrics =====
mantis_broker_api_calls_total = Counter(
    "mantis_broker_api_calls_total",
    "Total broker API calls",
    ["endpoint", "status"],  # status: success, error, timeout
)

mantis_broker_api_latency_seconds = Histogram(
    "mantis_broker_api_latency_seconds",
    "Broker API call latency in seconds",
    ["endpoint"],
)

mantis_broker_websocket_messages_total = Counter(
    "mantis_broker_websocket_messages_total",
    "Total WebSocket messages received",
    ["message_type"],  # quote, trade, heartbeat
)

# ===== Close Detection Metrics =====
close_detection_path_counter = Counter(
    "mantis_close_detection_path_total",
    "Close detection paths taken (primary, deferred, unreconciled)",
    ["path", "epic"],
)

# v2 shadow-mode observability: counts CloseDetector outcomes while v1 remains
# authoritative. Used to prove v2 agrees with v1 before promoting the flag.
close_detection_v2_shadow_counter = Counter(
    "mantis_close_detection_v2_shadow_total",
    "Close detection v2 outcomes observed in shadow mode (non-authoritative)",
    ["outcome", "epic"],  # outcome: reconciled|deferred|unreconciled|error
)

close_detection_shadow_disagreement_counter = Counter(
    "mantis_close_detection_shadow_disagreement_total",
    "Shadow disagreements between v1 (authoritative) and v2 (shadow)",
    ["v1_path", "v2_outcome", "epic"],
)

# ===== Paper Trading P&L Snapshot Metrics =====
# 60s scheduler observability — per-tick outcome counter so we can alarm on
# error spikes (broker dead, DB unreachable, etc.) without tailing logs.
paper_pnl_snapshot_counter = Counter(
    "mantis_paper_pnl_snapshot_total",
    "Paper trading 60s P&L snapshot ticks recorded by outcome",
    ["outcome"],  # success | empty | error
)

# ===== QW3 Spread Filter Metrics =====
# Per-asset-class spread filter blocks (paper_loop.py spread filter step 3b).
mantis_spread_filter_blocked_total = Counter(
    "mantis_spread_filter_blocked_total",
    "Trades blocked by the per-asset-class spread filter (QW3)",
    ["epic", "asset_class"],  # asset_class: crypto | precious | default
)

# ===== QW4 Calendar Gate Metrics =====
# Trades blocked (or would-be-blocked in log_only mode) by the economic
# calendar gate. `mode` distinguishes log_only (observation) from block
# (real gate) so dashboards can compute block-rate without confusing the
# two phases of the rollout.
mantis_calendar_gate_blocked_total = Counter(
    "mantis_calendar_gate_blocked_total",
    "Trades blocked by the economic calendar gate (QW4)",
    ["epic", "mode"],  # mode: log_only | block
)

# ===== QW5 Slippage Observability Metrics =====
# Captures the broker-side execution slippage (|fill_price - signal_price|)
# from the ExecutionEngine pipeline. Buckets tuned for typical price-scale
# slippage on Capital.com instruments (5-200 points absolute).
mantis_slippage_points = Histogram(
    "mantis_slippage_points",
    "Absolute execution slippage in price points (|fill - signal|)",
    ["epic", "direction"],
    buckets=(5, 10, 20, 30, 50, 75, 100, 150, 200, 500),
)
mantis_slippage_pct = Histogram(
    "mantis_slippage_pct",
    "Relative execution slippage as fraction of signal price",
    ["epic"],
    buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10),
)

# ===== QW5 Live WR Tracker =====
# Per-epic rolling live win rate over the analytics endpoint window (default
# 21d). Updated every time GET /api/analytics/live-wr is invoked. Includes
# delta vs the OOS expectation from optimal_thresholds.json.
mantis_live_wr_gauge = Gauge(
    "mantis_live_wr",
    "Per-epic rolling live win-rate (TP / decided trades)",
    ["epic"],
)
mantis_live_wr_oos_delta_gauge = Gauge(
    "mantis_live_wr_oos_delta",
    "Live WR minus OOS WR (negative = live underperforms OOS)",
    ["epic"],
)


class MetricsCollector:
    """
    Collector for updating Prometheus metrics from application state.
    Call update() periodically to refresh metrics.
    """

    @staticmethod
    def update_system_info(app_name: str, version: str, environment: str):
        """Update system information metrics."""
        mantis_info.info(
            {
                "app_name": app_name,
                "version": version,
                "environment": environment,
            }
        )

    @staticmethod
    def update_positions(positions: list[dict], mode: str):
        """
        Update position metrics.

        Args:
            positions: List of open positions
            mode: Trading mode (PAPER, DEMO, LIVE)
        """
        # Reset gauges
        mantis_open_positions_count._metrics.clear()

        # Count positions by epic and direction
        position_counts = {}
        for pos in positions:
            epic = pos.get("epic", "UNKNOWN")
            direction = pos.get("direction", "UNKNOWN")
            key = (epic, direction)
            position_counts[key] = position_counts.get(key, 0) + 1

        # Update gauges
        for (epic, direction), count in position_counts.items():
            mantis_open_positions_count.labels(epic=epic, direction=direction).set(count)

    @staticmethod
    def update_account_metrics(equity: float, daily_pnl: float, total_pnl: float, mode: str):
        """
        Update account metrics.

        Args:
            equity: Current account equity
            daily_pnl: Daily P&L
            total_pnl: Total P&L
            mode: Trading mode
        """
        mantis_account_equity.labels(mode=mode).set(equity)
        mantis_daily_pnl.labels(mode=mode).set(daily_pnl)
        mantis_total_pnl.labels(mode=mode).set(total_pnl)

    @staticmethod
    def record_trade_execution(
        epic: str,
        direction: str,
        outcome: str,
        duration_seconds: float | None = None,
    ):
        """
        Record a trade execution.

        Args:
            epic: Asset epic
            direction: BUY or SELL
            outcome: success, rejected, failed
            duration_seconds: Execution duration
        """
        mantis_trades_executed_total.labels(epic=epic, direction=direction, outcome=outcome).inc()

        if duration_seconds is not None:
            mantis_trade_execution_duration_seconds.labels(epic=epic).observe(duration_seconds)

    @staticmethod
    def record_signal(epic: str, direction: str, strategy: str, confidence: float):
        """
        Record a trading signal.

        Args:
            epic: Asset epic
            direction: BUY or SELL
            strategy: Strategy name
            confidence: Signal confidence (0-1)
        """
        mantis_signals_generated_total.labels(
            epic=epic, direction=direction, strategy=strategy
        ).inc()
        mantis_signal_confidence.labels(epic=epic).observe(confidence)

    @staticmethod
    def update_risk_metrics(
        daily_drawdown: float,
        total_drawdown: float,
        consecutive_losses: dict[str, int],
    ):
        """
        Update risk metrics.

        Args:
            daily_drawdown: Daily drawdown percentage
            total_drawdown: Total drawdown percentage
            consecutive_losses: Dict of consecutive losses by epic
        """
        mantis_drawdown_pct.labels(type="daily").set(daily_drawdown)
        mantis_drawdown_pct.labels(type="total").set(total_drawdown)

        for epic, count in consecutive_losses.items():
            mantis_consecutive_losses.labels(epic=epic).set(count)

    @staticmethod
    def record_circuit_breaker(epic: str, reason: str):
        """Record circuit breaker activation."""
        mantis_circuit_breaker_trips_total.labels(epic=epic, reason=reason).inc()

    @classmethod
    def record_close_detection(cls, *, path: str, epic: str, retry_count: int = 0) -> None:
        """Record the path taken for a close detection event.

        Args:
            path: 'primary' | 'deferred' | 'unreconciled'
            epic: asset epic (e.g. 'WTIUSD')
            retry_count: number of deferred retries before this path was taken
                (intentionally NOT a label to avoid cardinality explosion;
                exposed via logs instead)
        """
        try:
            close_detection_path_counter.labels(path=path, epic=epic).inc()
        except Exception:
            pass

    @classmethod
    def record_close_detection_v2_shadow(cls, *, outcome: str, epic: str) -> None:
        """Record a shadow-mode v2 outcome (not authoritative).

        Args:
            outcome: 'reconciled' | 'deferred' | 'unreconciled' | 'error'
            epic: asset epic
        """
        try:
            close_detection_v2_shadow_counter.labels(outcome=outcome, epic=epic).inc()
        except Exception:
            pass

    @classmethod
    def record_close_shadow_disagreement(cls, *, v1_path: str, v2_outcome: str, epic: str) -> None:
        """Record a per-deal disagreement between v1 (authoritative) and v2 (shadow)."""
        try:
            close_detection_shadow_disagreement_counter.labels(
                v1_path=v1_path, v2_outcome=v2_outcome, epic=epic
            ).inc()
        except Exception:
            pass

    @classmethod
    def record_calendar_gate_blocked(cls, *, epic: str, mode: str) -> None:
        """Record an economic-calendar blackout match (QW4).

        Args:
            epic: Asset epic
            mode: 'log_only' (would-block, trade still proceeded) or
                  'block' (actually rejected)
        """
        try:
            mantis_calendar_gate_blocked_total.labels(epic=epic, mode=mode).inc()
        except Exception:
            pass

    @classmethod
    def record_spread_filter_blocked(cls, *, epic: str, asset_class: str) -> None:
        """Record a QW3 spread-filter block.

        Args:
            epic: Asset epic (e.g., BTCUSD, XAUUSD, US500)
            asset_class: 'crypto' | 'precious' | 'default'
        """
        try:
            mantis_spread_filter_blocked_total.labels(
                epic=epic, asset_class=asset_class
            ).inc()
        except Exception:
            pass

    @classmethod
    def record_slippage(
        cls, *, epic: str, direction: str, signal_price: float, fill_price: float
    ) -> None:
        """Record execution slippage histograms (QW5).

        Captures both absolute (points) and relative (pct) slippage so we can
        attribute the H1 "TP almost hit but reversed" pattern to either entry
        slippage (high relative) or exit slippage (high absolute on big moves).
        """
        if signal_price <= 0 or fill_price <= 0:
            return
        try:
            slip_pts = abs(fill_price - signal_price)
            slip_pct = slip_pts / signal_price
            mantis_slippage_points.labels(epic=epic, direction=direction).observe(slip_pts)
            mantis_slippage_pct.labels(epic=epic).observe(slip_pct)
        except Exception:
            pass

    @classmethod
    def update_live_wr(
        cls, *, epic: str, live_wr: float, oos_delta: float | None
    ) -> None:
        """Push the latest live WR gauge for an epic (QW5)."""
        try:
            mantis_live_wr_gauge.labels(epic=epic).set(live_wr)
            if oos_delta is not None:
                mantis_live_wr_oos_delta_gauge.labels(epic=epic).set(oos_delta)
        except Exception:
            pass

    @classmethod
    def record_paper_pnl_snapshot(cls, *, outcome: str) -> None:
        """Record the outcome of a 60s paper-trading P&L snapshot tick.

        Args:
            outcome: 'success' (row written), 'empty' (no broker / no loop)
                     or 'error' (exception during persist).

        Cardinality is bounded by the three labels above — safe to keep
        unsampled. Used to alert when the scheduler stops succeeding.
        """
        try:
            paper_pnl_snapshot_counter.labels(outcome=outcome).inc()
        except Exception:
            pass

    @staticmethod
    def record_model_prediction(
        epic: str, model_type: str, predicted_class: str, confidence: float, duration: float
    ):
        """
        Record ML model prediction.

        Args:
            epic: Asset epic
            model_type: Model type (xgboost, lstm, etc.)
            predicted_class: Predicted class
            confidence: Prediction confidence
            duration: Inference time in seconds
        """
        mantis_model_prediction_total.labels(
            epic=epic, model_type=model_type, predicted_class=predicted_class
        ).inc()
        mantis_model_confidence.labels(epic=epic, model_type=model_type).observe(confidence)
        mantis_model_inference_duration_seconds.labels(epic=epic, model_type=model_type).observe(
            duration
        )
