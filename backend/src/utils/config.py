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
        default="http://localhost:4200,http://localhost:4321,http://localhost:8000", alias="CORS_ORIGINS"
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

    # ===== Broker Configuration =====
    use_demo: bool = Field(default=True, alias="USE_DEMO")
    session_timeout_minutes: int = Field(default=10, alias="SESSION_TIMEOUT_MINUTES")
    max_reconnect_attempts: int = Field(default=5, alias="MAX_RECONNECT_ATTEMPTS")
    reconnect_delay_seconds: int = Field(default=5, alias="RECONNECT_DELAY_SECONDS")
    rate_limit_requests_per_second: int = Field(
        default=10, alias="RATE_LIMIT_REQUESTS_PER_SECOND"
    )
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
    trading_enabled: bool = Field(default=False, alias="TRADING_ENABLED")
    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")
    execution_mode: str = Field(default="PAPER", alias="EXECUTION_MODE")
    min_confidence_threshold: float = Field(default=0.65, alias="MIN_CONFIDENCE_THRESHOLD")
    max_total_open_positions: int = Field(default=5, alias="MAX_TOTAL_OPEN_POSITIONS")
    max_total_exposure: float = Field(default=1.0, alias="MAX_TOTAL_EXPOSURE")

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
    scalp_chop_zone_min_confluence: int = Field(default=5, alias="SCALP_CHOP_ZONE_MIN_CONFLUENCE")
    scalp_chop_zone_start: int = Field(default=16, alias="SCALP_CHOP_ZONE_START")
    scalp_chop_zone_end: int = Field(default=20, alias="SCALP_CHOP_ZONE_END")
    scalp_tp1_risk_multiple: float = Field(default=0.5, alias="SCALP_TP1_RISK_MULTIPLE")
    scalp_tp2_risk_multiple: float = Field(default=1.5, alias="SCALP_TP2_RISK_MULTIPLE")
    scalp_dead_market_adx: float = Field(default=20.0, alias="SCALP_DEAD_MARKET_ADX")
    scalp_dead_market_bb_pctile: float = Field(default=20.0, alias="SCALP_DEAD_MARKET_BB_PCTILE")
    scalp_asset_exclusion_enabled: bool = Field(default=True, alias="SCALP_ASSET_EXCLUSION_ENABLED")
    scalp_asset_exclusion_lookback_days: int = Field(default=14, alias="SCALP_ASSET_EXCLUSION_LOOKBACK_DAYS")
    scalp_asset_exclusion_min_trades: int = Field(default=5, alias="SCALP_ASSET_EXCLUSION_MIN_TRADES")
    scalp_asset_exclusion_sharpe_threshold: float = Field(
        default=-0.5, alias="SCALP_ASSET_EXCLUSION_SHARPE_THRESHOLD"
    )

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
    rag_vector_store_path: str = Field(default="data/rag/vector_store", alias="RAG_VECTOR_STORE_PATH")

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
    access_token_expire_minutes: int = Field(
        default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(
        default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS"
    )

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
    backup_schedule_cron: str = Field(default="0 2 * * *", alias="BACKUP_SCHEDULE_CRON")  # 2 AM daily
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
