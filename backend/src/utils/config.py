"""
Configuration management using pydantic-settings.
Loads settings from environment variables and .env file.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== Application =====
    app_name: str = Field(default="AlgoTrader AI", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )

    # ===== FastAPI =====
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_reload: bool = Field(default=True, alias="API_RELOAD")
    cors_origins_str: str = Field(
        default="http://localhost:4200,http://localhost:4321,http://localhost:8000",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins_str.split(",")]

    # ===== Capital.com API - Demo =====
    capital_demo_api_url: str = Field(
        default="https://demo-api-capital.backend-capital.com", alias="CAPITAL_DEMO_API_URL"
    )
    capital_demo_ws_url: str = Field(
        default="wss://api-streaming-capital.backend-capital.com/connect",
        alias="CAPITAL_DEMO_WS_URL",
    )
    capital_demo_api_key: str = Field(alias="CAPITAL_DEMO_API_KEY")
    capital_demo_email: str = Field(alias="CAPITAL_DEMO_EMAIL")
    capital_demo_password: str = Field(alias="CAPITAL_DEMO_PASSWORD")

    @field_validator("capital_demo_api_key", "capital_demo_email", "capital_demo_password")
    @classmethod
    def validate_demo_credentials(cls, v: str, info) -> str:
        """Validate that demo credentials are not empty."""
        if not v or not v.strip():
            raise ValueError(
                f"{info.field_name} is required for demo mode. "
                f"Please configure it in your .env file."
            )
        return v.strip()

    # ===== Capital.com API - Live =====
    capital_live_api_url: str = Field(
        default="https://api-capital.backend-capital.com", alias="CAPITAL_LIVE_API_URL"
    )
    capital_live_ws_url: str = Field(
        default="wss://api-streaming-capital.backend-capital.com/connect",
        alias="CAPITAL_LIVE_WS_URL",
    )
    capital_live_api_key: str = Field(default="", alias="CAPITAL_LIVE_API_KEY")
    capital_live_email: str = Field(default="", alias="CAPITAL_LIVE_EMAIL")
    capital_live_password: str = Field(default="", alias="CAPITAL_LIVE_PASSWORD")

    # --- Forward Demo Lab (experiment account, isolated from soak) ---
    # Dedicated Capital.com API key for the forward-lab — separate session/CST
    # from the soak (which uses the default CAPITAL_DEMO_* creds). Same underlying
    # Capital.com account; isolation is per-session and verified before any live order.
    capital_experiment_api_key: str = Field(default="", alias="CAPITAL_EXPERIMENT_API_KEY")
    capital_experiment_email: str = Field(default="", alias="CAPITAL_EXPERIMENT_EMAIL")
    capital_experiment_password: str = Field(default="", alias="CAPITAL_EXPERIMENT_PASSWORD")
    capital_experiment_account_id: str | None = None
    forward_lab_notional_usd: float = 200.0
    forward_lab_max_concurrent: int = 5
    forward_lab_daily_loss_limit_usd: float = 100.0
    forward_lab_gap_threshold: float = 0.01
    forward_lab_eod_flatten_utc: str = "20:45"  # HH:MM UTC cash-session flatten
    forward_lab_orb_or_window_min: int = 30  # opening-range minutes (Yahoo delay -> 30)
    forward_lab_orb_watch_end_utc: str = "16:00"  # breakout watch cutoff (UTC)
    forward_lab_orb_rvol_min: float = 1.5  # min relative volume to be "in play"
    forward_lab_orb_top_k: int = 5  # max in-play names per day
    forward_lab_orb_breakout_buffer: float = 0.0  # fraction beyond OR required
    forward_lab_orb_stop_atr_mult: float = 1.0  # SL ATR floor multiplier

    # ===== Auth Gate =====
    # When True, every state-changing API endpoint requires a valid JWT.
    # Default False so the existing test fixtures (which don't ship
    # Authorization headers) keep passing under DEMO/PAPER. LIVE deploy
    # MUST set this True — main.py refuses to start a non-DEMO backend
    # otherwise (see C1-API audit fix).
    auth_required: bool = Field(default=False, alias="AUTH_REQUIRED")

    # ===== Broker Configuration =====
    use_demo: bool = Field(default=True, alias="USE_DEMO")
    session_timeout_minutes: int = Field(default=10, alias="SESSION_TIMEOUT_MINUTES")
    max_reconnect_attempts: int = Field(default=5, alias="MAX_RECONNECT_ATTEMPTS")
    reconnect_delay_seconds: int = Field(default=5, alias="RECONNECT_DELAY_SECONDS")
    rate_limit_requests_per_second: int = Field(default=10, alias="RATE_LIMIT_REQUESTS_PER_SECOND")
    # HIGH-2 FIX: Broker retry configuration for transient 5xx errors
    broker_retry_attempts: int = Field(default=3, alias="BROKER_RETRY_ATTEMPTS")
    broker_retry_base_delay: float = Field(default=0.5, alias="BROKER_RETRY_BASE_DELAY")  # seconds
    # HIGH-3 FIX: Configurable deal confirmation delay (was hardcoded 300ms)
    deal_confirmation_delay: float = Field(default=0.3, alias="DEAL_CONFIRMATION_DELAY")  # seconds

    @property
    def capital_ws_url(self) -> str:
        """Get the active Capital.com WebSocket URL based on use_demo flag."""
        return self.capital_demo_ws_url if self.use_demo else self.capital_live_ws_url

    # HTTP Timeouts
    http_timeout_seconds: int = Field(default=30, alias="HTTP_TIMEOUT_SECONDS")
    http_connect_timeout_seconds: int = Field(default=10, alias="HTTP_CONNECT_TIMEOUT_SECONDS")

    # ===== PostgreSQL =====
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="algotrader", alias="POSTGRES_DB")
    postgres_user: str = Field(default="algotrader", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")

    @property
    def database_url(self) -> str:
        """
        Construct PostgreSQL database URL.

        WARNING: Contains plain-text password. Never log this value directly.
        Use safe_database_url for logging purposes.
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def safe_database_url(self) -> str:
        """
        Construct PostgreSQL database URL with masked password for logging.
        Safe to use in logs and error messages.
        """
        return (
            f"postgresql://{self.postgres_user}:***@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    # ===== DuckDB =====
    duckdb_path: str = Field(default="data/analytics.duckdb", alias="DUCKDB_PATH")
    duckdb_read_only: bool = Field(default=False, alias="DUCKDB_READ_ONLY")

    # ===== Redis =====
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: str = Field(default="", alias="REDIS_PASSWORD")
    redis_max_connections: int = Field(default=50, alias="REDIS_MAX_CONNECTIONS")

    @property
    def redis_url(self) -> str:
        """
        Construct Redis URL.

        WARNING: Contains plain-text password. Never log this value directly.
        Use safe_redis_url for logging purposes.
        """
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def safe_redis_url(self) -> str:
        """
        Construct Redis URL with masked password for logging.
        Safe to use in logs and error messages.
        """
        if self.redis_password:
            return f"redis://:***@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ===== Data Pipeline =====
    data_dir: str = Field(default="data/historical", alias="DATA_DIR")
    parquet_compression: Literal["snappy", "gzip", "brotli", "zstd"] = Field(
        default="snappy", alias="PARQUET_COMPRESSION"
    )
    historical_data_assets_str: str = Field(
        default="XAUUSD,BTCUSD,US500,WTIUSD,EURUSD,NVDA,TSLA,XAGUSD,DE40",
        alias="HISTORICAL_DATA_ASSETS",
    )
    historical_data_timeframes_str: str = Field(
        default="1min,5min,15min,1h,4h,1d", alias="HISTORICAL_DATA_TIMEFRAMES"
    )
    max_historical_days: int = Field(default=730, alias="MAX_HISTORICAL_DAYS")

    @property
    def historical_data_assets(self) -> list[str]:
        """Parse assets from comma-separated string."""
        return [asset.strip() for asset in self.historical_data_assets_str.split(",")]

    @property
    def historical_data_timeframes(self) -> list[str]:
        """Parse timeframes from comma-separated string."""
        return [tf.strip() for tf in self.historical_data_timeframes_str.split(",")]

    # ===== Machine Learning =====
    model_dir: str = Field(default="data/models", alias="MODEL_DIR")
    device: Literal["cuda", "cpu", "mps"] = Field(default="cpu", alias="DEVICE")
    train_batch_size: int = Field(default=64, alias="TRAIN_BATCH_SIZE")
    eval_batch_size: int = Field(default=128, alias="EVAL_BATCH_SIZE")

    # ===== Risk Management =====
    max_risk_per_trade: float = Field(default=0.02, alias="MAX_RISK_PER_TRADE")
    max_daily_drawdown: float = Field(default=0.05, alias="MAX_DAILY_DRAWDOWN")
    max_total_drawdown: float = Field(default=0.15, alias="MAX_TOTAL_DRAWDOWN")
    cb_daily_loss_limit: float = Field(default=0.10, alias="CB_DAILY_LOSS_LIMIT")

    # ===== Trading =====
    initial_capital: float = Field(default=11000.0, alias="INITIAL_CAPITAL")
    max_spread_pct: float = Field(
        default=0.15, alias="MAX_SPREAD_PCT"
    )  # Max spread as % of TP distance
    cross_asset_enabled: bool = Field(default=False, alias="CROSS_ASSET_ENABLED")
    correlation_regime_enabled: bool = Field(default=False, alias="CORRELATION_REGIME_ENABLED")
    correlation_regime_threshold: float = Field(default=0.75, alias="CORRELATION_REGIME_THRESHOLD")
    correlation_regime_size_reduction: float = Field(
        default=0.50, alias="CORRELATION_REGIME_SIZE_REDUCTION"
    )
    # Phase 1 expansion 2026-05-23: dynamic correlation matrix flag,
    # decoupled from `correlation_regime_enabled` (Phase 2 panic regime).
    # When True, paper_loop refreshes the NxN correlation matrix in
    # `CorrelationGuard` every 30 min using the full self.epics basket
    # (no `[:10]` cap). Used by `RiskManager.check_trade` step 5 to
    # downsize correlated exposures via `check_exposure_dynamic`.
    dynamic_correlation_enabled: bool = Field(default=True, alias="DYNAMIC_CORRELATION_ENABLED")
    # Minimum number of epics with sufficient candle data (>=100 bars)
    # required before computing the correlation matrix. Below this floor
    # the refresh is skipped and the prior matrix (or static-pair fallback)
    # is used.
    dynamic_correlation_bootstrap_min_assets: int = Field(
        default=5, alias="DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS"
    )
    # Close-detection reconciliation: how long to wait for a transaction match
    # before giving up and finalising a pending close with a heuristic P&L.
    close_reconciliation_timeout_seconds: int = Field(
        default=600, alias="CLOSE_RECONCILIATION_TIMEOUT_SECONDS"
    )  # 10 minutes
    # Close-detection v2 rollout flag. When False, paper_loop uses the legacy
    # transaction-first matcher. When True, paper_loop additionally runs the
    # activity-first CloseDetector in shadow mode (v1 remains authoritative for
    # DB writes and alerting). Promotion to primary happens after 24h of
    # zero-disagreement shadow traffic.
    close_detection_v2_enabled: bool = Field(default=False, alias="CLOSE_DETECTION_V2_ENABLED")
    # Dedicated reconciler sub-loop. When True, broker-position reconciliation
    # (_detect_broker_closed, _update_trailing_stops, _check_stop_losses) runs
    # in a separate asyncio.Task at RECONCILER_INTERVAL_SECONDS cadence,
    # decoupled from the strategy signal loop. When False (default), legacy
    # behavior: all three calls happen inside _run_iteration at the strategy
    # tick cadence (SCALP_CHECK_INTERVAL).
    reconciler_dedicated_enabled: bool = Field(default=False, alias="RECONCILER_DEDICATED_ENABLED")
    reconciler_interval_seconds: int = Field(default=15, alias="RECONCILER_INTERVAL_SECONDS")
    # Strategy signal loop bar-alignment. When True, the strategy loop wakes
    # at exact UTC bar-close boundaries (e.g. 4h grid → 00:00/04:00/08:00/
    # 12:00/16:00/20:00 UTC) + a small offset to let the broker publish the
    # new candle. Cuts up-to-`interval_seconds` jitter between bar close and
    # signal generation. Requires RECONCILER_DEDICATED_ENABLED=true so SL
    # guards keep running on the 15s reconciler task while the strategy loop
    # waits for the next slot. When False (legacy), the loop sleeps a fixed
    # `interval_seconds` regardless of bar boundaries.
    signal_loop_align_to_bar: bool = Field(default=True, alias="SIGNAL_LOOP_ALIGN_TO_BAR")
    signal_loop_post_bar_offset_seconds: int = Field(
        default=10, alias="SIGNAL_LOOP_POST_BAR_OFFSET_SECONDS"
    )
    # Per-epic risk multiplier applied immediately after position-sizing in
    # RiskManager.check_trade. Composes with correlation, confidence, and
    # equity-curve multipliers. Use to reduce exposure on chronic losers
    # without removing them from TRADABLE_ASSETS (signals still generate +
    # audit), or to boost proven winners.
    #
    # Format: "EPIC=mult,EPIC=mult" — parsed by `epic_risk_multipliers`
    # property. 0.0 ⇒ RiskManager rejects every signal for that epic
    # (full disable, audit visible). 1.0 ⇒ baseline. >1.0 ⇒ boost.
    # Missing epics default to 1.0.
    #
    # Calibration source: 2026-05-08 production P&L analysis.
    #   - Chronic losers (cumulative > -$3k): ETHUSD/DE40/US500 → 0.0
    #   - Mid-range losers (-$1k to -$3k):
    #     BTCUSD/SOLUSD/NVDA/COPPER → 0.5
    #   - Proven winners: TSLA (+$2.2k) / USDJPY (+$1.1k, 75% WR) → 1.5
    epic_risk_multipliers_str: str = Field(default="", alias="EPIC_RISK_MULTIPLIERS")
    # ===== LLM Provider (Phase 14: local Ollama, 2026-05-08) =====
    # Backend abstraction for text gen + vision + embeddings. Default
    # routes everything to the GX10 NVIDIA AI box on the LAN — zero
    # token cost, sub-second warm latency on qwen3.6:35b. The Anthropic
    # Claude API path is preserved as a future backend (not implemented
    # in Phase 14a) for cloud deployments where the GX10 is not
    # reachable.
    llm_backend: str = Field(default="ollama", alias="LLM_BACKEND")
    ollama_base_url: str = Field(default="http://192.168.3.191:11434", alias="OLLAMA_BASE_URL")
    ollama_generation_model: str = Field(default="qwen3.6:35b", alias="OLLAMA_GENERATION_MODEL")
    ollama_vision_model: str = Field(default="qwen2.5vl:7b", alias="OLLAMA_VISION_MODEL")
    ollama_embedding_model: str = Field(default="bge-m3:latest", alias="OLLAMA_EMBEDDING_MODEL")
    ollama_embedding_dim: int = Field(default=1024, alias="OLLAMA_EMBEDDING_DIM")
    # `keep_alive=-1` pins the generation model in VRAM forever so
    # qwen3.6 doesn't get evicted by other tenants. Vision model
    # tolerates eviction since cold start is ~25s and we run at most
    # 90 inferences/day (15 epics × 6 four-hour bars).
    ollama_keep_alive_generation: str | int = Field(
        default=-1, alias="OLLAMA_KEEP_ALIVE_GENERATION"
    )
    ollama_keep_alive_vision: str = Field(default="1h", alias="OLLAMA_KEEP_ALIVE_VISION")
    ollama_timeout_seconds: float = Field(default=60.0, alias="OLLAMA_TIMEOUT_SECONDS")

    @property
    def epic_risk_multipliers(self) -> dict[str, float]:
        """Parse `EPIC_RISK_MULTIPLIERS` env into a dict.

        Tokens malformed/non-float are silently skipped so a typo in
        config never accidentally disables every epic.
        """
        out: dict[str, float] = {}
        for token in (self.epic_risk_multipliers_str or "").split(","):
            token = token.strip()
            if not token or "=" not in token:
                continue
            epic, mult = token.split("=", 1)
            try:
                out[epic.strip().upper()] = float(mult.strip())
            except ValueError:
                continue
        return out

    # Forex with USD as the base currency (USDJPY, USDCHF, USDCAD) has a
    # pip value much smaller than $1 per micro-unit, so the standard
    # max_position_pct (~20% notional) caps the size at a level where
    # SL/TP P&L is only a few cents — uneconomical against spread+slippage.
    # This multiplier scales the per-trade exposure cap for USD-base
    # forex pairs only, leveraging the broker's higher leverage tier
    # (Capital.com forex demo: 30:1 retail, can be higher pro-tier).
    # Default 60.0 (post 2026-04-30) produces a USDJPY cap of ~60x the
    # stock-equivalent cap so the post-sizing risk floor (MIN_RISK_AMOUNT_USD)
    # can actually be met under typical MR stop_distance (~0.5–1 JPY).
    # Bumped from 30.0 after live observation: USDJPY landed at ~$1.46 risk
    # under cap-bounded sizing, far below the user-target ~$10/hit.
    # Stocks/crypto/commodities/indices unaffected.
    forex_usd_base_size_multiplier: float = Field(
        default=60.0, alias="FOREX_USD_BASE_SIZE_MULTIPLIER"
    )

    # Mean Reversion Strategy
    mr_primary_enabled: bool = Field(default=False, alias="MR_PRIMARY_ENABLED")
    mr_min_quality: float = Field(default=0.55, alias="MR_MIN_QUALITY")
    mr_z_entry: float = Field(default=2.0, alias="MR_Z_ENTRY")
    mr_z_stop: float = Field(default=3.0, alias="MR_Z_STOP")
    mr_adx_max: float = Field(default=30.0, alias="MR_ADX_MAX")
    # Minimum TP distance as a fraction of entry price. FOREX ATR is so
    # small (USDJPY ATR ~0.05 on price ~159 = 0.03%) that the
    # `TP_MAX_ATR * atr` cap drives unrewardable micro-targets. The floor
    # ensures every trade has at least 0.15% (or 0.20% for forex) of room
    # to be worth the round-trip cost. SL is widened proportionally so
    # the realised R:R from `SL_ATR_MULT/TP_MAX_ATR` is preserved.
    mr_min_tp_pct: float = Field(default=0.0015, alias="MR_MIN_TP_PCT")
    mr_min_tp_pct_forex: float = Field(default=0.0020, alias="MR_MIN_TP_PCT_FOREX")
    # Minimum notional position size in USD. Without it the
    # `max_position_pct` cap shrinks forex micro-trades to a few units
    # ($500-ish notional) where slippage + spread eat the entire edge.
    # The floor lifts the size up to a meaningful $200 minimum, still
    # bounded by `max_position_pct` so it can't blow past the risk cap.
    min_notional_usd: float = Field(default=200.0, alias="MIN_NOTIONAL_USD")
    # Minimum *risk* amount in USD (post-sizing).
    # MIN_NOTIONAL_USD lifts the position notional but, on forex pairs
    # where the quote currency is not USD (USDJPY), the actual USD risk
    # of a trade can still be a few cents because notional ≠ risk.
    # Risk is `position_size × stop_distance` converted to USD via the
    # quote currency. Trades whose computed risk falls below this floor
    # are first lifted (capped by `max_position_pct`) and rejected with
    # `error.min_risk` if the lift would breach the exposure cap.
    # Bumped 2026-04-30: $5 → $10 to match user target of ~1‰ equity per
    # SL/TP hit (≈ $11 on $11k initial). Sub-$10 forex trades produced
    # $0.02–$1.46 P&L per hit in production — uneconomical noise.
    min_risk_amount_usd: float = Field(default=10.0, alias="MIN_RISK_AMOUNT_USD")
    # Maximum dynamic leverage multiplier the floor-lift path may push to
    # in step 7-bis when the standard `forex_usd_base_size_multiplier` cap
    # cannot reach `min_risk_amount_usd`. Set higher than the standard
    # multiplier so a 97%-confidence forex signal with a tight stop never
    # gets rejected just because the conservative day-one cap (60×) only
    # produced ~$4 risk — instead the cap is auto-elevated up to this
    # ceiling for that single trade. Capital.com forex demo / pro tier
    # supports up to ~200:1 effective; 200× keeps the worst-case single-
    # position margin around 60–70% of equity (still leaves room for one
    # concurrent non-forex trade). Audit shows the actual multiplier used
    # so monitoring can spot trades that need very high leverage to clear
    # the floor.
    forex_max_leverage_multiplier: float = Field(
        default=200.0, alias="FOREX_MAX_LEVERAGE_MULTIPLIER"
    )
    # Minimum acceptable Risk:Reward on a strategy-paired (suggested_stop +
    # suggested_tp) signal. Backstop for stale-snapshot bugs where a
    # strategy emits TP next to entry — produced 2026-05-04 TSLA trades
    # with R:R 0.02–0.21 (entry 389.14, SL 396.77, TP 388.99). The pair-
    # as-is rule (rule 6) trusted the strategy's calibration even when
    # the calibration produced a degenerate ratio. This floor REJECTS
    # such signals at risk-manager step 4-bis without mixing risk-mgr SL
    # with strategy TP (which would re-introduce the 2026-04-28 inversion
    # bug). Set to 0.40 = TP must be at least 40% of SL distance for the
    # trade to clear.
    min_signal_rr_threshold: float = Field(default=0.40, alias="MIN_SIGNAL_RR_THRESHOLD")

    # ===== Entry-Drift Handler =====
    # Drift = (broker live mid - signal.entry_price) / signal.entry_price.
    # signal.entry_price is the candle close at prediction time (stale by
    # up to one candle). Real fill happens at broker live price. When the
    # two diverge the strategy-calibrated SL/TP — and the R:R floor — are
    # computed on a phantom entry, producing degenerate trades (META BUY
    # closed in <1 min at $1.28 TP on 2026-05-13; same root cause as TSLA
    # 2026-05-04 and BTCUSD 2026-05-04 partial-close loop).
    #
    # Strategy:
    #   - drift_pct < deadband        → no-op (tick noise)
    #   - deadband ≤ drift_pct ≤ cap  → SHIFT SL/TP by absolute delta,
    #                                   preserves R:R distance
    #   - drift_pct > cap             → REJECT (signal features invalid
    #                                   on the new price; gap / news /
    #                                   broker halt etc.)
    # Stocks get a wider cap because intraday gaps on regular-session
    # open are routine; forex/crypto/indices stay tight.
    entry_drift_deadband_pct: float = Field(default=0.001, alias="ENTRY_DRIFT_DEADBAND_PCT")
    max_entry_drift_shift_pct: float = Field(default=0.01, alias="MAX_ENTRY_DRIFT_SHIFT_PCT")
    max_entry_drift_shift_pct_stocks: float = Field(
        default=0.02, alias="MAX_ENTRY_DRIFT_SHIFT_PCT_STOCKS"
    )

    # ADX minimum threshold — blocks neutral zone 15-22 in signal generation
    # (StrategyConfig.adx_ranging_threshold default aligned, see strategy/schemas.py)
    adx_min_threshold: float = Field(default=22.0, alias="ADX_MIN_THRESHOLD", ge=10.0, le=50.0)

    # Trailing TP1 fraction — strategy-anchored partial-close midpoint.
    # When strategy supplies take_profit, TP1 = entry + tp1_fraction * (TP - entry).
    # Lifted 0.50 -> 0.70 on 2026-05-15 (QW6) to capture more effective
    # realized R on winning trades. See risk/trailing_stop_manager.py.
    tp1_fraction: float = Field(default=0.70, alias="TP1_FRACTION", ge=0.1, le=1.0)

    # Per-asset-class spread filter limits (QW3 2026-05-15).
    # Applied at paper_loop.py spread filter step 3b. Threshold compares
    # spread_ratio = (offer - bid) / tp_distance against the asset class limit.
    # Selected via get_spread_limit(epic) helper; max_spread_pct (above)
    # kept as legacy/global fallback if class lookup ever returns None.
    spread_limit_crypto: float = Field(default=0.15, alias="SPREAD_LIMIT_CRYPTO", ge=0.01, le=1.0)
    spread_limit_precious: float = Field(
        default=0.12, alias="SPREAD_LIMIT_PRECIOUS", ge=0.01, le=1.0
    )
    spread_limit_default: float = Field(default=0.08, alias="SPREAD_LIMIT_DEFAULT", ge=0.01, le=1.0)

    # Regime Gate (Phase 2)
    regime_gate_enabled: bool = Field(default=False, alias="REGIME_GATE_ENABLED")
    regime_gate_confidence_threshold: float = Field(
        default=0.65, alias="REGIME_GATE_CONFIDENCE_THRESHOLD"
    )
    regime_gate_psi_threshold: float = Field(default=0.20, alias="REGIME_GATE_PSI_THRESHOLD")
    regime_gate_top_features: int = Field(default=30, alias="REGIME_GATE_TOP_FEATURES")
    trading_enabled: bool = Field(default=False, alias="TRADING_ENABLED")
    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")
    execution_mode: str = Field(default="PAPER", alias="EXECUTION_MODE")
    min_confidence_threshold: float = Field(default=0.65, alias="MIN_CONFIDENCE_THRESHOLD")
    max_total_open_positions: int = Field(default=10, alias="MAX_TOTAL_OPEN_POSITIONS")
    max_total_exposure: float = Field(default=1.0, alias="MAX_TOTAL_EXPOSURE")

    # ===== Close Detection (State Recovery) =====
    orphan_reinject_max_age_days: int = Field(default=2, alias="ORPHAN_REINJECT_MAX_AGE_DAYS")

    # ===== Scalp Strategy =====
    scalp_mode_enabled: bool = Field(default=False, alias="SCALP_MODE_ENABLED")
    scalp_candle_resolution: str = Field(default="15min", alias="SCALP_CANDLE_RESOLUTION")
    scalp_check_interval: int = Field(default=60, alias="SCALP_CHECK_INTERVAL")
    scalp_score_threshold: int = Field(default=55, alias="SCALP_SCORE_THRESHOLD")
    scalp_score_full_threshold: int = Field(default=70, alias="SCALP_SCORE_FULL_THRESHOLD")
    scalp_sl_multiplier: float = Field(default=1.5, alias="SCALP_SL_MULTIPLIER")
    scalp_dynamic_sl_min: float = Field(default=1.0, alias="SCALP_DYNAMIC_SL_MIN")
    scalp_dynamic_sl_max: float = Field(default=3.0, alias="SCALP_DYNAMIC_SL_MAX")
    scalp_tp_risk_reward: float = Field(default=2.0, alias="SCALP_TP_RISK_REWARD")
    scalp_signal_dedup_seconds: int = Field(default=900, alias="SCALP_SIGNAL_DEDUP_SECONDS")
    scalp_max_open_positions: int = Field(default=3, alias="SCALP_MAX_OPEN_POSITIONS")
    scalp_max_risk_per_trade: float = Field(default=0.01, alias="SCALP_MAX_RISK_PER_TRADE")
    scalp_max_trades_per_day: int = Field(default=30, alias="SCALP_MAX_TRADES_PER_DAY")
    scalp_htf_enabled: bool = Field(default=True, alias="SCALP_HTF_ENABLED")
    scalp_htf_gate_enabled: bool = Field(default=True, alias="SCALP_HTF_GATE_ENABLED")
    scalp_max_hold_hours: float = Field(default=12.0, alias="SCALP_MAX_HOLD_HOURS")
    # MR hard time-stop: ~3 bars on 4h = 12h. Literature says 70-80% of profitable
    # MR trades close within 1-3 bars. 24h was too generous — live data showed
    # positions drifting 16h+ without hitting TP or SL (dead trades).
    mr_max_hold_hours: float = Field(default=12.0, alias="MR_MAX_HOLD_HOURS")
    # MR Fix #3 (memory project_mr_pending_improvements): when enabled,
    # paper_loop computes a per-epic OU half-life (AR(1) regression on
    # 4h close residuals) and uses it as the time-stop ceiling, capped
    # at mr_max_hold_hours. False → original fixed 12h behaviour.
    mr_ou_halflife_enabled: bool = Field(default=False, alias="MR_OU_HALFLIFE_ENABLED")
    mr_ou_halflife_bar_hours: float = Field(default=4.0, alias="MR_OU_HALFLIFE_BAR_HOURS")
    mr_ou_halflife_lookback_bars: int = Field(default=30, alias="MR_OU_HALFLIFE_LOOKBACK_BARS")
    mr_ou_halflife_candle_history_bars: int = Field(
        default=200, alias="MR_OU_HALFLIFE_CANDLE_HISTORY_BARS"
    )
    scalp_chop_zone_min_confluence: int = Field(default=5, alias="SCALP_CHOP_ZONE_MIN_CONFLUENCE")
    scalp_chop_zone_start: int = Field(default=16, alias="SCALP_CHOP_ZONE_START")
    scalp_chop_zone_end: int = Field(default=20, alias="SCALP_CHOP_ZONE_END")
    scalp_tp1_risk_multiple: float = Field(default=0.5, alias="SCALP_TP1_RISK_MULTIPLE")
    scalp_tp2_risk_multiple: float = Field(default=1.5, alias="SCALP_TP2_RISK_MULTIPLE")
    scalp_dead_market_adx: float = Field(default=20.0, alias="SCALP_DEAD_MARKET_ADX")
    scalp_dead_market_bb_pctile: float = Field(default=20.0, alias="SCALP_DEAD_MARKET_BB_PCTILE")
    scalp_asset_exclusion_enabled: bool = Field(default=True, alias="SCALP_ASSET_EXCLUSION_ENABLED")
    scalp_asset_exclusion_lookback_days: int = Field(
        default=14, alias="SCALP_ASSET_EXCLUSION_LOOKBACK_DAYS"
    )
    scalp_asset_exclusion_min_trades: int = Field(
        default=5, alias="SCALP_ASSET_EXCLUSION_MIN_TRADES"
    )
    scalp_asset_exclusion_sharpe_threshold: float = Field(
        default=-0.5, alias="SCALP_ASSET_EXCLUSION_SHARPE_THRESHOLD"
    )

    # ===== ML-Primary Mode =====
    ml_primary_enabled: bool = Field(default=False, alias="ML_PRIMARY_ENABLED")
    ml_primary_min_confidence: float = Field(default=0.45, alias="ML_PRIMARY_MIN_CONFIDENCE")
    ml_primary_min_technical_quality: float = Field(
        default=0.25, alias="ML_PRIMARY_MIN_TECHNICAL_QUALITY"
    )
    ml_primary_vwap_penalty: float = Field(default=0.70, alias="ML_PRIMARY_VWAP_PENALTY")
    ml_primary_htf_penalty: float = Field(default=0.60, alias="ML_PRIMARY_HTF_PENALTY")

    # ===== External APIs =====
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    marketaux_api_key: str = Field(default="", alias="MARKETAUX_API_KEY")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")
    twelve_data_api_key: str = Field(default="", alias="TWELVE_DATA_API_KEY")
    fred_api_key: str = Field(default="", alias="FRED_API_KEY")

    # ===== Signal Intelligence Layer (SIL) =====
    sil_enabled: bool = Field(default=False, alias="SIL_ENABLED")
    sil_cache_ttl_minutes: int = Field(default=60, alias="SIL_CACHE_TTL_MINUTES")
    sil_calendar_gate_enabled: bool = Field(default=True, alias="SIL_CALENDAR_GATE_ENABLED")
    sil_calendar_minutes_before: int = Field(default=30, alias="SIL_CALENDAR_MINUTES_BEFORE")
    sil_calendar_minutes_after: int = Field(default=15, alias="SIL_CALENDAR_MINUTES_AFTER")

    # ===== Economic Calendar Gate Activation Mode (QW4 2026-05-15) =====
    # Decouples the calendar gate from the SIL master flag so the gate can
    # rollout independently. Mode controls what happens on a blackout match:
    #   off       — gate skipped entirely (legacy behavior when sil_enabled
    #               was the only switch)
    #   log_only  — detect + log + Prometheus counter, DO NOT block trade
    #               (safe 48h rollout before flipping to block)
    #   block     — full gating: reject new entry with reason="ECONOMIC_CALENDAR_GATE"
    #
    # Default 'log_only' ships the observability without changing behavior
    # so we can measure block-rate before committing to the real gate.
    calendar_gate_mode: str = Field(
        default="log_only", alias="CALENDAR_GATE_MODE", pattern="^(off|log_only|block)$"
    )
    nasdaq_data_link_api_key: str = Field(default="", alias="NASDAQ_DATA_LINK_API_KEY")

    # ===== Multi-Agent System (Sprint 1) =====
    agents_enabled: bool = Field(default=False, alias="AGENTS_ENABLED")
    agents_llm_model: str = Field(default="claude-sonnet-4-20250514", alias="AGENTS_LLM_MODEL")
    agents_temperature: float = Field(default=0.2, alias="AGENTS_TEMPERATURE")
    agents_max_tokens: int = Field(default=2000, alias="AGENTS_MAX_TOKENS")
    agents_technical_weight: float = Field(default=0.4, alias="AGENTS_TECHNICAL_WEIGHT")
    agents_sentiment_weight: float = Field(default=0.2, alias="AGENTS_SENTIMENT_WEIGHT")
    agents_risk_weight: float = Field(default=0.4, alias="AGENTS_RISK_WEIGHT")
    agents_risk_block_threshold: float = Field(default=0.8, alias="AGENTS_RISK_BLOCK_THRESHOLD")
    agents_debate_enabled: bool = Field(default=True, alias="AGENTS_DEBATE_ENABLED")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # ===== Reinforcement Learning (Sprint 2) =====
    rl_enabled: bool = Field(default=False, alias="RL_ENABLED")
    rl_algorithm: str = Field(default="PPO", alias="RL_ALGORITHM")
    rl_reward_function: str = Field(default="composite", alias="RL_REWARD_FUNCTION")
    rl_sliding_window_size: int = Field(default=500, alias="RL_SLIDING_WINDOW_SIZE")
    rl_retrain_interval_minutes: int = Field(default=60, alias="RL_RETRAIN_INTERVAL")
    rl_max_trades_per_session: int = Field(default=20, alias="RL_MAX_TRADES_PER_SESSION")
    rl_target_hold_candles: int = Field(default=10, alias="RL_TARGET_HOLD_CANDLES")
    rl_max_drawdown_pct: float = Field(default=0.01, alias="RL_MAX_DRAWDOWN_PCT")
    rl_learning_rate: float = Field(default=3e-4, alias="RL_LEARNING_RATE")
    rl_total_timesteps: int = Field(default=50000, alias="RL_TOTAL_TIMESTEPS")

    # ===== Memory System (Sprint 3) =====
    memory_enabled: bool = Field(default=False, alias="MEMORY_ENABLED")
    memory_stm_max_signals: int = Field(default=50, alias="MEMORY_STM_MAX_SIGNALS")
    memory_stm_max_trades: int = Field(default=20, alias="MEMORY_STM_MAX_TRADES")
    memory_decay_lambda: float = Field(default=0.1, alias="MEMORY_DECAY_LAMBDA")
    memory_consolidation_hours: int = Field(default=24, alias="MEMORY_CONSOLIDATION_HOURS")
    memory_episodic_threshold: float = Field(default=0.8, alias="MEMORY_EPISODIC_THRESHOLD")
    memory_db_path: str = Field(default="data/memory/mantis_memory.db", alias="MEMORY_DB_PATH")

    # ===== Vision AI (Sprint 4) =====
    vision_enabled: bool = Field(default=False, alias="VISION_ENABLED")
    vision_llm_model: str = Field(default="claude-sonnet-4-20250514", alias="VISION_LLM_MODEL")
    vision_chart_width: int = Field(default=1200, alias="VISION_CHART_WIDTH")
    vision_chart_height: int = Field(default=600, alias="VISION_CHART_HEIGHT")

    # ===== RAG Pipeline (Sprint 4) =====
    rag_enabled: bool = Field(default=False, alias="RAG_ENABLED")
    rag_max_context_tokens: int = Field(default=2000, alias="RAG_MAX_CONTEXT_TOKENS")
    rag_news_lookback_hours: int = Field(default=4, alias="RAG_NEWS_LOOKBACK_HOURS")
    rag_vector_store_path: str = Field(
        default="data/rag/vector_store", alias="RAG_VECTOR_STORE_PATH"
    )

    # ===== DRL Ensemble (Sprint 5) =====
    drl_enabled: bool = Field(default=False, alias="DRL_ENABLED")
    drl_algorithms: str = Field(default="PPO,SAC,A2C,TD3", alias="DRL_ALGORITHMS")
    drl_voting_mode: str = Field(default="REGIME_ROUTING", alias="DRL_VOTING_MODE")
    drl_confidence_threshold: float = Field(default=0.6, alias="DRL_CONFIDENCE_THRESHOLD")
    drl_ensemble_weight: float = Field(default=0.25, alias="DRL_ENSEMBLE_WEIGHT")
    drl_total_timesteps: int = Field(default=50000, alias="DRL_TOTAL_TIMESTEPS")
    drl_retrain_interval_days: int = Field(default=7, alias="DRL_RETRAIN_INTERVAL_DAYS")
    drl_train_test_split: float = Field(default=0.8, alias="DRL_TRAIN_TEST_SPLIT")
    drl_sliding_window_candles: int = Field(default=2000, alias="DRL_SLIDING_WINDOW_CANDLES")
    drl_min_sharpe_for_deploy: float = Field(default=0.5, alias="DRL_MIN_SHARPE_DEPLOY")
    drl_max_drawdown_for_deploy: float = Field(default=0.15, alias="DRL_MAX_DD_DEPLOY")

    # ===== Security =====
    secret_key: str = Field(default="dev_secret_key_change_in_production", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Warn if using default secret key."""
        if v == "dev_secret_key_change_in_production":
            import warnings

            warnings.warn(
                "Using default SECRET_KEY — set a strong key in .env for production!",
                UserWarning,
                stacklevel=2,
            )
        return v

    encryption_key: str = Field(
        default="", alias="ENCRYPTION_KEY", description="Fernet encryption key (32 bytes base64)"
    )
    encryption_enabled: bool = Field(
        default=False, alias="ENCRYPTION_ENABLED", description="Enable secrets encryption"
    )

    # ===== Alerting =====
    alerts_enabled: bool = Field(default=False, alias="ALERTS_ENABLED")
    alert_email_enabled: bool = Field(default=False, alias="ALERT_EMAIL_ENABLED")
    alert_email_smtp_host: str = Field(default="", alias="ALERT_EMAIL_SMTP_HOST")
    alert_email_smtp_port: int = Field(default=587, alias="ALERT_EMAIL_SMTP_PORT")
    alert_email_smtp_user: str = Field(default="", alias="ALERT_EMAIL_SMTP_USER")
    alert_email_smtp_password: str = Field(default="", alias="ALERT_EMAIL_SMTP_PASSWORD")
    alert_email_from: str = Field(default="alerts@mantis.ai", alias="ALERT_EMAIL_FROM")
    alert_email_to: str = Field(default="", alias="ALERT_EMAIL_TO")  # Comma-separated
    alert_slack_enabled: bool = Field(default=False, alias="ALERT_SLACK_ENABLED")
    alert_slack_webhook_url: str = Field(default="", alias="ALERT_SLACK_WEBHOOK_URL")
    alert_webhook_enabled: bool = Field(default=False, alias="ALERT_WEBHOOK_ENABLED")
    alert_webhook_url: str = Field(default="", alias="ALERT_WEBHOOK_URL")
    alert_telegram_enabled: bool = Field(default=False, alias="ALERT_TELEGRAM_ENABLED")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    alert_drawdown_threshold_pct: float = Field(default=10.0, alias="ALERT_DRAWDOWN_THRESHOLD_PCT")
    alert_consecutive_losses_threshold: int = Field(
        default=5, alias="ALERT_CONSECUTIVE_LOSSES_THRESHOLD"
    )

    # ===== Database Backups =====
    backup_enabled: bool = Field(default=False, alias="BACKUP_ENABLED")
    backup_dir: str = Field(default="data/backups", alias="BACKUP_DIR")
    backup_schedule_cron: str = Field(
        default="0 2 * * *", alias="BACKUP_SCHEDULE_CRON"
    )  # 2 AM daily
    backup_retention_days: int = Field(default=30, alias="BACKUP_RETENTION_DAYS")

    # ===== Rate Limiting =====
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_per_minute: int = Field(default=100, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_second: int = Field(default=10, alias="RATE_LIMIT_PER_SECOND")
    rate_limit_trade_per_minute: int = Field(default=5, alias="RATE_LIMIT_TRADE_PER_MINUTE")


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()
