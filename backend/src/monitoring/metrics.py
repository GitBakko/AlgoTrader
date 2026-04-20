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
    def record_close_detection(
        cls, *, path: str, epic: str, retry_count: int = 0
    ) -> None:
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
