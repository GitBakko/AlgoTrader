# Scalp Hybrid Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the failing swing trading system (1H, 15% WR) with a hybrid scalp system using multi-indicator scoring on 15-min candles, with ML as a confirmation boost layer.

**Architecture:** New `ScalpScoreStrategy` implements `BaseStrategy`, computes a 0-100 score from 6 technical indicators (EMA, RSI, MACD, Volume, ADX, BB Squeeze). The paper loop switches from 1H/300s checks to 15min/60s checks. Risk parameters tighten (SL 1.0 ATR, TP 2.0 RR, max 3 positions). ML acts as size modifier: agrees → full, neutral → half, disagrees → skip.

**Tech Stack:** Python 3.12+, Polars, XGBoost (existing), pytest

**Branch:** `feature/scalp-hybrid-strategy`

**Test command:** `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short -x`

---

### Task 1: Add Scalp Config Parameters

**Files:**
- Modify: `backend/src/utils/config.py` (Settings class, around line 200)
- Modify: `backend/.env` (add new defaults)

**Step 1: Add new config fields to Settings class**

In `backend/src/utils/config.py`, after the existing risk management section (~line 212), add:

```python
    # ===== Scalp Strategy =====
    scalp_candle_resolution: str = Field(default="15min", alias="SCALP_CANDLE_RESOLUTION")
    scalp_check_interval: int = Field(default=60, alias="SCALP_CHECK_INTERVAL")
    scalp_score_threshold: int = Field(default=60, alias="SCALP_SCORE_THRESHOLD")
    scalp_score_full_threshold: int = Field(default=75, alias="SCALP_SCORE_FULL_THRESHOLD")
    scalp_sl_multiplier: float = Field(default=1.0, alias="SCALP_SL_MULTIPLIER")
    scalp_tp_risk_reward: float = Field(default=2.0, alias="SCALP_TP_RISK_REWARD")
    scalp_signal_dedup_seconds: int = Field(default=900, alias="SCALP_SIGNAL_DEDUP_SECONDS")
    scalp_max_open_positions: int = Field(default=3, alias="SCALP_MAX_OPEN_POSITIONS")
    scalp_max_risk_per_trade: float = Field(default=0.01, alias="SCALP_MAX_RISK_PER_TRADE")
    scalp_mode_enabled: bool = Field(default=False, alias="SCALP_MODE_ENABLED")
```

**Step 2: Add to `.env`**

```env
# Scalp Hybrid Strategy
SCALP_MODE_ENABLED=true
SCALP_CANDLE_RESOLUTION=15min
SCALP_CHECK_INTERVAL=60
SCALP_SCORE_THRESHOLD=60
SCALP_SCORE_FULL_THRESHOLD=75
SCALP_SL_MULTIPLIER=1.0
SCALP_TP_RISK_REWARD=2.0
SCALP_SIGNAL_DEDUP_SECONDS=900
SCALP_MAX_OPEN_POSITIONS=3
SCALP_MAX_RISK_PER_TRADE=0.01
```

**Step 3: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_config.py -v --tb=short -x 2>&1 | tail -20
```

Expected: All existing config tests pass (new fields have defaults so they're backward-compatible).

**Step 4: Commit**

```bash
git add backend/src/utils/config.py backend/.env
git commit -m "feat: add scalp strategy config parameters"
```

---

### Task 2: Create ScalpScoreStrategy

**Files:**
- Create: `backend/src/strategy/scalp_score_strategy.py`
- Create: `backend/tests/strategy/test_scalp_score_strategy.py`

**Step 1: Write the test file**

Create `backend/tests/strategy/test_scalp_score_strategy.py`:

```python
"""Tests for ScalpScoreStrategy multi-indicator scoring."""
import polars as pl
import pytest

from src.strategy.scalp_score_strategy import ScalpScoreStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.models.schemas import SignalClass


@pytest.fixture
def strategy() -> ScalpScoreStrategy:
    return ScalpScoreStrategy()


@pytest.fixture
def config() -> StrategyConfig:
    return StrategyConfig(
        epic="XAUUSD",
        stop_multiplier=1.0,
        risk_reward_ratio=2.0,
    )


@pytest.fixture
def recent_bars() -> pl.DataFrame:
    """Minimal recent bars for lookback (20 rows)."""
    return pl.DataFrame({
        "close": [100.0 + i * 0.1 for i in range(20)],
        "high": [100.5 + i * 0.1 for i in range(20)],
        "low": [99.5 + i * 0.1 for i in range(20)],
        "volume": [1000 + i * 10 for i in range(20)],
    })


def _make_bar(**overrides) -> dict:
    """Create a current_bar dict with sensible defaults."""
    bar = {
        "close": 105.0,
        "high": 105.5,
        "low": 104.5,
        "open": 104.8,
        "volume": 1500,
        "atr_14": 1.0,
        "rsi_14": 40.0,
        "ema_9": 105.1,
        "ema_21": 104.8,
        "macd_histogram": 0.3,
        "macd": 0.5,
        "macd_signal": 0.2,
        "adx_14": 25.0,
        "volume_sma_20": 1200,
        "bb_upper": 106.0,
        "bb_lower": 104.0,
        "bb_middle": 105.0,
        "keltner_upper": 106.5,
        "keltner_lower": 103.5,
    }
    bar.update(overrides)
    return bar


class TestScalpScoreStrategyProperties:
    def test_name(self, strategy):
        assert strategy.name == "scalp_score"

    def test_applicable_regimes(self, strategy):
        regimes = strategy.applicable_regimes
        assert "trending_up" in regimes
        assert "trending_down" in regimes
        assert "ranging" in regimes


class TestScalpScoreHold:
    def test_hold_on_invalid_price(self, strategy, recent_bars, config):
        bar = _make_bar(close=0)
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD

    def test_hold_on_invalid_atr(self, strategy, recent_bars, config):
        bar = _make_bar(atr_14=0)
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD

    def test_hold_on_low_score(self, strategy, recent_bars, config):
        """Conflicting signals should produce low score → HOLD."""
        bar = _make_bar(
            ema_9=104.5, ema_21=105.2,  # bearish EMA
            rsi_14=50.0,                  # neutral RSI
            macd_histogram=-0.1,          # weak bearish MACD
            adx_14=12.0,                  # no trend
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD


class TestScalpScoreBuy:
    def test_strong_buy_signal(self, strategy, recent_bars, config):
        """All indicators aligned bullish → strong BUY."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # bullish cross
            rsi_14=38.0,                     # oversold bounce
            macd_histogram=0.5,              # strong bullish
            macd=0.6, macd_signal=0.1,       # recent crossover
            adx_14=28.0,                     # strong trend
            volume=1500, volume_sma_20=1000, # high volume
            bb_upper=106.0, bb_lower=104.0,  # normal BB
            keltner_upper=106.5, keltner_lower=103.5,
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence > 0.6
        assert signal.suggested_stop is not None
        assert signal.suggested_tp is not None
        assert signal.suggested_stop < signal.entry_price < signal.suggested_tp

    def test_buy_stop_loss_distance(self, strategy, recent_bars, config):
        """SL should be ~1.0 ATR below entry for BUY."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=38.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=28.0,
            volume=1500, volume_sma_20=1000,
            atr_14=2.0,
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        if signal.direction == SignalDirection.BUY:
            sl_distance = signal.entry_price - signal.suggested_stop
            assert 1.5 <= sl_distance <= 2.5  # ~1.0 * ATR(2.0)


class TestScalpScoreSell:
    def test_strong_sell_signal(self, strategy, recent_bars, config):
        """All indicators aligned bearish → strong SELL."""
        bar = _make_bar(
            close=105.0,
            ema_9=104.5, ema_21=105.2,     # bearish cross
            rsi_14=65.0,                     # overbought area
            macd_histogram=-0.5,             # strong bearish
            macd=-0.6, macd_signal=-0.1,     # recent bearish crossover
            adx_14=28.0,                     # strong trend
            volume=1500, volume_sma_20=1000, # high volume
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence > 0.6
        assert signal.suggested_stop is not None
        assert signal.suggested_tp is not None
        assert signal.suggested_tp < signal.entry_price < signal.suggested_stop


class TestScalpScoreBacktest:
    def test_backtest_adds_columns(self, strategy):
        df = pl.DataFrame({
            "close": [100.0, 101.0, 102.0, 103.0, 104.0] * 10,
            "high": [100.5, 101.5, 102.5, 103.5, 104.5] * 10,
            "low": [99.5, 100.5, 101.5, 102.5, 103.5] * 10,
            "open": [99.8, 100.8, 101.8, 102.8, 103.8] * 10,
            "volume": [1000] * 50,
            "atr_14": [1.0] * 50,
            "rsi_14": [50.0] * 50,
            "ema_9": [101.0] * 50,
            "ema_21": [100.5] * 50,
            "macd_histogram": [0.1] * 50,
            "macd": [0.2] * 50,
            "macd_signal": [0.1] * 50,
            "adx_14": [25.0] * 50,
            "volume_sma_20": [1000] * 50,
            "bb_upper": [103.0] * 50,
            "bb_lower": [97.0] * 50,
            "bb_middle": [100.0] * 50,
            "keltner_upper": [104.0] * 50,
            "keltner_lower": [96.0] * 50,
        })
        result = strategy.generate_backtest_signals(df, "XAUUSD", "15min")
        assert "signal_direction" in result.columns
        assert "signal_confidence" in result.columns
        assert len(result) == len(df)
```

**Step 2: Run test to verify it fails**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_strategy.py -v --tb=short 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.strategy.scalp_score_strategy'`

**Step 3: Implement ScalpScoreStrategy**

Create `backend/src/strategy/scalp_score_strategy.py`:

```python
"""
ScalpScoreStrategy — Multi-indicator scoring for 15-min scalping.

Computes a composite score (0-100) from 6 technical indicators:
  EMA Trend (20), RSI (18), MACD (18), Volume (12), ADX (18), BB Squeeze (14)

Score >= 60 → entry signal (BUY or SELL depending on indicator alignment).
ML model acts as a boost layer externally (not inside this strategy).
"""

import polars as pl
from loguru import logger

from src.models.schemas import SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal

# Indicator weights (must sum to 100)
W_EMA = 20
W_RSI = 18
W_MACD = 18
W_VOLUME = 12
W_ADX = 18
W_BB = 14

# Score thresholds
DEFAULT_ENTRY_THRESHOLD = 60
DEFAULT_FULL_SIZE_THRESHOLD = 75


class ScalpScoreStrategy(BaseStrategy):
    """Multi-indicator scoring strategy for scalp/intraday trading."""

    def __init__(
        self,
        entry_threshold: int = DEFAULT_ENTRY_THRESHOLD,
        full_size_threshold: int = DEFAULT_FULL_SIZE_THRESHOLD,
    ):
        self.entry_threshold = entry_threshold
        self.full_size_threshold = full_size_threshold

    @property
    def name(self) -> str:
        return "scalp_score"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down", "ranging"]

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_ema(ema_9: float, ema_21: float, price: float) -> tuple[float, float]:
        """
        EMA cross + slope scoring.
        Returns (buy_score, sell_score) each in [0, W_EMA].
        """
        if ema_9 <= 0 or ema_21 <= 0:
            return 0.0, 0.0

        spread = (ema_9 - ema_21) / ema_21  # positive = bullish
        # Slope: how far price is from EMA9
        slope = (price - ema_9) / ema_9 if ema_9 > 0 else 0

        buy_score = 0.0
        sell_score = 0.0

        if spread > 0:
            # Bullish: EMA9 above EMA21
            buy_score = min(W_EMA, W_EMA * min(spread * 200, 1.0))  # 0.5% spread = full points
            if slope > 0:
                buy_score = min(W_EMA, buy_score * 1.2)  # Bonus for price above EMA9
        elif spread < 0:
            # Bearish: EMA9 below EMA21
            sell_score = min(W_EMA, W_EMA * min(abs(spread) * 200, 1.0))
            if slope < 0:
                sell_score = min(W_EMA, sell_score * 1.2)

        return buy_score, sell_score

    @staticmethod
    def _score_rsi(rsi: float) -> tuple[float, float]:
        """
        RSI scoring for buy/sell.
        BUY zone: RSI 30-45 (oversold bounce).
        SELL zone: RSI 55-70 (overbought rejection).
        """
        buy_score = 0.0
        sell_score = 0.0

        if 25 <= rsi <= 45:
            # Peak score at RSI ~35
            buy_score = W_RSI * max(0, 1.0 - abs(rsi - 35) / 15)
        elif 55 <= rsi <= 75:
            # Peak score at RSI ~65
            sell_score = W_RSI * max(0, 1.0 - abs(rsi - 65) / 15)

        return buy_score, sell_score

    @staticmethod
    def _score_macd(histogram: float, macd: float, signal: float) -> tuple[float, float]:
        """
        MACD histogram + crossover scoring.
        """
        buy_score = 0.0
        sell_score = 0.0

        if histogram > 0:
            buy_score += W_MACD * 0.6  # Histogram positive
            if macd > signal:
                buy_score += W_MACD * 0.4  # Crossover confirmed
        elif histogram < 0:
            sell_score += W_MACD * 0.6
            if macd < signal:
                sell_score += W_MACD * 0.4

        return min(W_MACD, buy_score), min(W_MACD, sell_score)

    @staticmethod
    def _score_volume(volume: float, volume_sma: float) -> float:
        """
        Volume confirmation (direction-agnostic).
        Returns score in [0, W_VOLUME].
        """
        if volume_sma <= 0:
            return 0.0
        ratio = volume / volume_sma
        if ratio >= 1.2:
            return min(W_VOLUME, W_VOLUME * min((ratio - 1.0) / 0.5, 1.0))
        return 0.0

    @staticmethod
    def _score_adx(adx: float) -> float:
        """
        ADX trend strength (direction-agnostic).
        Returns score in [0, W_ADX].
        """
        if adx >= 30:
            return W_ADX  # Strong trend
        elif adx >= 20:
            return W_ADX * (adx - 15) / 15  # Linear ramp from 15 to 30
        return 0.0

    @staticmethod
    def _score_bb_squeeze(
        bb_upper: float, bb_lower: float,
        keltner_upper: float, keltner_lower: float,
        price: float, bb_middle: float,
    ) -> tuple[float, float]:
        """
        Bollinger Band squeeze + breakout direction.
        Squeeze: BB inside Keltner (compression).
        Breakout up → buy points; breakout down → sell points.
        """
        buy_score = 0.0
        sell_score = 0.0

        if bb_upper <= 0 or keltner_upper <= 0:
            return 0.0, 0.0

        bb_width = bb_upper - bb_lower
        kc_width = keltner_upper - keltner_lower

        if kc_width <= 0:
            return 0.0, 0.0

        # Squeeze detection: BB narrower than Keltner
        is_squeeze = bb_width < kc_width
        squeeze_ratio = 1.0 - (bb_width / kc_width) if is_squeeze else 0.0

        if squeeze_ratio > 0:
            # Breakout direction from squeeze
            if price > bb_middle:
                buy_score = W_BB * min(squeeze_ratio * 2, 1.0)
            elif price < bb_middle:
                sell_score = W_BB * min(squeeze_ratio * 2, 1.0)
        elif price > bb_upper:
            # Breaking above upper BB (strong momentum)
            buy_score = W_BB * 0.5
        elif price < bb_lower:
            # Breaking below lower BB
            sell_score = W_BB * 0.5

        return buy_score, sell_score

    # ------------------------------------------------------------------
    # Main signal generation
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        price = float(current_bar.get("close", 0))
        atr = float(current_bar.get("atr_14", 0))

        if price <= 0 or atr <= 0:
            return self._hold(epic, price)

        # Extract indicators
        ema_9 = float(current_bar.get("ema_9", 0))
        ema_21 = float(current_bar.get("ema_21", 0))
        rsi = float(current_bar.get("rsi_14", 50))
        macd_hist = float(current_bar.get("macd_histogram", 0))
        macd_val = float(current_bar.get("macd", 0))
        macd_sig = float(current_bar.get("macd_signal", 0))
        adx = float(current_bar.get("adx_14", 0))
        volume = float(current_bar.get("volume", 0))
        volume_sma = float(current_bar.get("volume_sma_20", 0))
        bb_upper = float(current_bar.get("bb_upper", 0))
        bb_lower = float(current_bar.get("bb_lower", 0))
        bb_middle = float(current_bar.get("bb_middle", 0))
        kc_upper = float(current_bar.get("keltner_upper", 0))
        kc_lower = float(current_bar.get("keltner_lower", 0))

        # Compute component scores
        ema_buy, ema_sell = self._score_ema(ema_9, ema_21, price)
        rsi_buy, rsi_sell = self._score_rsi(rsi)
        macd_buy, macd_sell = self._score_macd(macd_hist, macd_val, macd_sig)
        vol_score = self._score_volume(volume, volume_sma)
        adx_score = self._score_adx(adx)
        bb_buy, bb_sell = self._score_bb_squeeze(
            bb_upper, bb_lower, kc_upper, kc_lower, price, bb_middle
        )

        buy_total = ema_buy + rsi_buy + macd_buy + vol_score + adx_score + bb_buy
        sell_total = ema_sell + rsi_sell + macd_sell + vol_score + adx_score + bb_sell

        # Determine direction: highest score wins
        if buy_total >= sell_total and buy_total >= self.entry_threshold:
            direction = SignalDirection.BUY
            score = buy_total
            signal_class = SignalClass.BUY
        elif sell_total > buy_total and sell_total >= self.entry_threshold:
            direction = SignalDirection.SELL
            score = sell_total
            signal_class = SignalClass.SELL
        else:
            return self._hold(epic, price)

        # Confidence: map score to [0.0, 1.0]
        confidence = min(1.0, score / 100.0)

        # SL / TP from config
        sl_mult = config.stop_multiplier  # 1.0 ATR for scalp
        rr = config.risk_reward_ratio     # 2.0 for scalp

        if direction == SignalDirection.BUY:
            stop = price - atr * sl_mult
            tp = price + atr * sl_mult * rr
        else:
            stop = price + atr * sl_mult
            tp = price - atr * sl_mult * rr

        logger.debug(
            f"[{epic}] ScalpScore: BUY={buy_total:.0f} SELL={sell_total:.0f} "
            f"-> {direction.value} (score={score:.0f}, conf={confidence:.2f})"
        )

        return TradingSignal(
            epic=epic,
            direction=direction,
            confidence=confidence,
            signal_class=signal_class,
            entry_price=price,
            suggested_stop=stop,
            suggested_tp=tp,
            technical_confirmation=True,
            strategy_name=self.name,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """Vectorized backtest signal generation."""
        directions = []
        confidences = []

        rows = ohlc_df.to_dicts()
        config = StrategyConfig(
            epic=epic,
            timeframe=timeframe,
            stop_multiplier=1.0,
            risk_reward_ratio=2.0,
        )
        dummy_recent = pl.DataFrame({"close": [0.0]})

        for row in rows:
            sig = self.generate_signal(epic, row, dummy_recent, config)
            dir_val = {"BUY": 1, "SELL": -1, "HOLD": 0}[sig.direction.value]
            directions.append(dir_val)
            confidences.append(sig.confidence)

        return ohlc_df.with_columns([
            pl.Series("signal_direction", directions),
            pl.Series("signal_confidence", confidences),
            pl.lit(None).alias("signal_stop"),
            pl.lit(None).alias("signal_tp"),
        ])

    @staticmethod
    def _hold(epic: str, price: float) -> TradingSignal:
        return TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=SignalClass.HOLD,
            entry_price=price,
            technical_confirmation=False,
        )
```

**Step 4: Run tests to verify they pass**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_strategy.py -v --tb=short 2>&1 | tail -20
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add backend/src/strategy/scalp_score_strategy.py backend/tests/strategy/test_scalp_score_strategy.py
git commit -m "feat: create ScalpScoreStrategy with multi-indicator scoring"
```

---

### Task 3: Wire ScalpScoreStrategy into StrategyManager

**Files:**
- Modify: `backend/src/strategy/strategy_manager.py`
- Create: `backend/tests/strategy/test_strategy_manager_scalp.py`

**Step 1: Write the test**

Create `backend/tests/strategy/test_strategy_manager_scalp.py`:

```python
"""Tests for StrategyManager with scalp mode integration."""
import pytest
from unittest.mock import MagicMock

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.strategy_manager import StrategyManager
from src.strategy.schemas import SignalDirection


@pytest.fixture
def scalp_manager() -> StrategyManager:
    """StrategyManager in scalp mode."""
    return StrategyManager(scalp_mode=True)


@pytest.fixture
def prediction_buy() -> PredictionResult:
    return PredictionResult(
        signal_class=SignalClass.BUY,
        confidence=0.65,
        probabilities=[0.1, 0.25, 0.65],
    )


@pytest.fixture
def prediction_hold() -> PredictionResult:
    return PredictionResult(
        signal_class=SignalClass.HOLD,
        confidence=0.35,
        probabilities=[0.3, 0.4, 0.3],
    )


@pytest.fixture
def prediction_sell() -> PredictionResult:
    return PredictionResult(
        signal_class=SignalClass.SELL,
        confidence=0.70,
        probabilities=[0.70, 0.20, 0.10],
    )


@pytest.fixture
def bullish_market_data() -> dict:
    """Market data with strong bullish indicators → should score high BUY."""
    return {
        "current_price": 105.0,
        "atr": 1.0,
        "rsi": 38.0,
        "adx": 28.0,
        "regime": "trending_up",
        "ema_9": 105.5,
        "ema_21": 104.8,
        "macd_histogram": 0.5,
        "macd": 0.6,
        "macd_signal": 0.1,
        "volume": 1500,
        "volume_sma_20": 1000,
        "bb_upper": 106.0,
        "bb_lower": 104.0,
        "bb_middle": 105.0,
        "keltner_upper": 106.5,
        "keltner_lower": 103.5,
    }


class TestScalpModeSignalGeneration:
    def test_scalp_mode_uses_score_strategy(self, scalp_manager, prediction_buy, bullish_market_data):
        """In scalp mode, technical score should drive the signal."""
        signal = scalp_manager.process_prediction(prediction_buy, "XAUUSD", bullish_market_data)
        assert signal.strategy_name == "scalp_score"

    def test_ml_agree_keeps_full_confidence(self, scalp_manager, prediction_buy, bullish_market_data):
        """When ML agrees with technical BUY, confidence stays high."""
        signal = scalp_manager.process_prediction(prediction_buy, "XAUUSD", bullish_market_data)
        assert signal.direction == SignalDirection.BUY
        # ML agrees (BUY) → no penalty
        assert signal.confidence > 0.5

    def test_ml_hold_halves_confidence(self, scalp_manager, prediction_hold, bullish_market_data):
        """When ML says HOLD, technical signal's confidence is halved."""
        signal = scalp_manager.process_prediction(prediction_hold, "XAUUSD", bullish_market_data)
        # Technical says BUY, ML says HOLD → confidence reduced
        if signal.direction == SignalDirection.BUY:
            assert signal.confidence <= 0.5  # halved

    def test_ml_disagree_blocks_signal(self, scalp_manager, prediction_sell, bullish_market_data):
        """When ML strongly disagrees (SELL vs technical BUY), signal blocked."""
        signal = scalp_manager.process_prediction(prediction_sell, "XAUUSD", bullish_market_data)
        # Technical says BUY, ML says SELL with high confidence → HOLD
        assert signal.direction == SignalDirection.HOLD
```

**Step 2: Modify `strategy_manager.py` to add scalp mode**

Add `scalp_mode` parameter to `__init__` and a new `_process_scalp` method. The key change: when `scalp_mode=True`, use `ScalpScoreStrategy` as primary signal, then apply ML boost.

```python
# Add to imports at top:
from src.strategy.scalp_score_strategy import ScalpScoreStrategy

# Modify __init__ to accept scalp_mode:
def __init__(
    self,
    configs: dict[str, StrategyConfig] | None = None,
    excluded_epics: set[str] | None = None,
    scalp_mode: bool = False,
):
    self._configs = configs or {}
    self.excluded_epics: set[str] = excluded_epics or set()
    self.scalp_mode = scalp_mode
    self._scalp_strategy = ScalpScoreStrategy() if scalp_mode else None

# Modify process_prediction to route:
def process_prediction(self, prediction, epic, market_data):
    if self.scalp_mode:
        return self._process_scalp(prediction, epic, market_data)
    # ... existing code unchanged ...

# Add new method:
def _process_scalp(
    self,
    prediction: PredictionResult,
    epic: str,
    market_data: dict,
) -> TradingSignal:
    """Scalp mode: technical score first, ML as boost."""
    import polars as pl
    from src.strategy.schemas import SignalDirection, StrategyConfig
    from src.models.schemas import SignalClass

    current_price = market_data.get("current_price")
    atr = market_data.get("atr")
    if current_price is None or atr is None:
        raise ValueError("market_data must contain 'current_price' and 'atr'")
    if not (isinstance(current_price, (int, float)) and current_price > 0):
        raise ValueError(f"Invalid current_price: {current_price}")
    if not (isinstance(atr, (int, float)) and atr > 0):
        raise ValueError(f"Invalid ATR: {atr}")

    config = self._get_config(epic)
    # Override for scalp: tighter stops
    config = StrategyConfig(
        epic=epic,
        stop_multiplier=1.0,
        risk_reward_ratio=2.0,
        min_confidence=0.40,
    )

    # Build current_bar from market_data
    current_bar = {
        "close": current_price,
        "atr_14": atr,
        "rsi_14": market_data.get("rsi", 50),
        "adx_14": market_data.get("adx", 0),
        "ema_9": market_data.get("ema_9", 0),
        "ema_21": market_data.get("ema_21", 0),
        "macd_histogram": market_data.get("macd_histogram", 0),
        "macd": market_data.get("macd", 0),
        "macd_signal": market_data.get("macd_signal", 0),
        "volume": market_data.get("volume", 0),
        "volume_sma_20": market_data.get("volume_sma_20", 0),
        "bb_upper": market_data.get("bb_upper", 0),
        "bb_lower": market_data.get("bb_lower", 0),
        "bb_middle": market_data.get("bb_middle", 0),
        "keltner_upper": market_data.get("keltner_upper", 0),
        "keltner_lower": market_data.get("keltner_lower", 0),
    }

    recent_bars = pl.DataFrame({"close": [current_price]})

    # Step 1: Technical score signal
    signal = self._scalp_strategy.generate_signal(epic, current_bar, recent_bars, config)

    if signal.direction == SignalDirection.HOLD:
        logger.info(f"Scalp [{epic}]: HOLD (score too low)")
        return signal

    # Step 2: ML boost layer
    ml_direction = {
        SignalClass.BUY: SignalDirection.BUY,
        SignalClass.SELL: SignalDirection.SELL,
        SignalClass.HOLD: SignalDirection.HOLD,
    }.get(prediction.signal_class, SignalDirection.HOLD)

    if ml_direction == signal.direction and prediction.confidence > 0.40:
        # ML agrees → full confidence (no change)
        logger.info(
            f"Scalp [{epic}]: {signal.direction.value} "
            f"(score→signal, ML agrees conf={prediction.confidence:.2f})"
        )
    elif ml_direction == SignalDirection.HOLD or prediction.confidence <= 0.40:
        # ML neutral → halve confidence
        signal.confidence *= 0.5
        logger.info(
            f"Scalp [{epic}]: {signal.direction.value} "
            f"(score→signal, ML neutral → half conf={signal.confidence:.2f})"
        )
    else:
        # ML disagrees (opposite direction with high confidence) → SKIP
        if prediction.confidence > 0.50:
            logger.info(
                f"Scalp [{epic}]: SKIP (technical={signal.direction.value}, "
                f"ML={ml_direction.value} conf={prediction.confidence:.2f})"
            )
            return TradingSignal(
                epic=epic,
                direction=SignalDirection.HOLD,
                confidence=0.0,
                signal_class=SignalClass.HOLD,
                entry_price=current_price,
                technical_confirmation=False,
                strategy_name="scalp_score",
            )
        else:
            # ML weakly disagrees → halve
            signal.confidence *= 0.5

    signal.strategy_name = "scalp_score"
    return signal
```

**Step 3: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_strategy_manager_scalp.py tests/strategy/test_strategy_manager.py -v --tb=short 2>&1 | tail -20
```

Expected: All tests PASS (new and existing).

**Step 4: Commit**

```bash
git add backend/src/strategy/strategy_manager.py backend/tests/strategy/test_strategy_manager_scalp.py
git commit -m "feat: wire ScalpScoreStrategy into StrategyManager with ML boost"
```

---

### Task 4: Modify Paper Loop for 15-min Candles

**Files:**
- Modify: `backend/src/trading/paper_loop.py` (lines 33, 60, 103, 692-714)

**Step 1: Make CHECK_INTERVAL and candle resolution configurable**

In `paper_loop.py`:

1. Line 33: Change `CHECK_INTERVAL = 300` to read from settings:
```python
from src.utils.config import get_settings
_settings = get_settings()
CHECK_INTERVAL = _settings.scalp_check_interval if _settings.scalp_mode_enabled else 300
```

2. Line 103: Change dedup window:
```python
self._signal_dedup_window_seconds = (
    _settings.scalp_signal_dedup_seconds if _settings.scalp_mode_enabled else 60
)
```

3. Lines 692-714: Make `_has_new_candle` use configurable resolution:
```python
def _has_new_candle(self, epic: str) -> bool:
    """Check if there's a new candle since last processed."""
    if self.data_access is None:
        return True
    try:
        resolution = _settings.scalp_candle_resolution if _settings.scalp_mode_enabled else "1h"
        latest = self.data_access.get_latest_price(epic, timeframe=resolution)
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
        return True
```

**Step 2: Update PredictionService.predict() call to pass resolution**

In `_process_epic` (~line 896): The `PredictionService.predict()` may need the resolution. Check if it uses a hardcoded timeframe internally. If so, it should be passed through. If it already reads from config, no change needed.

**Step 3: Run existing paper_loop tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_paper_loop.py -v --tb=short -x 2>&1 | tail -30
```

Expected: Existing tests pass (scalp_mode_enabled defaults to False so behavior unchanged).

**Step 4: Commit**

```bash
git add backend/src/trading/paper_loop.py
git commit -m "feat: make paper loop candle resolution and check interval configurable"
```

---

### Task 5: Adjust Risk Parameters for Scalp Mode

**Files:**
- Modify: `backend/src/risk/risk_manager.py` (lines 160-194, ~250-260)
- Modify: `backend/src/risk/stop_manager.py` (lines 14-15)

**Step 1: Make SL/TP multipliers scalp-aware in risk_manager.py**

In `check_trade()`, around line 160, read from settings:

```python
from src.utils.config import get_settings
_settings = get_settings()

# In check_trade():
if _settings.scalp_mode_enabled:
    base_sl = _settings.scalp_sl_multiplier  # 1.0
    rr_ratio = _settings.scalp_tp_risk_reward  # 2.0
    max_positions = _settings.scalp_max_open_positions  # 3
    risk_per_trade = _settings.scalp_max_risk_per_trade  # 0.01
else:
    base_sl = 2.0
    rr_ratio = 2.5
    max_positions = self.risk_limits.max_total_open_positions
    risk_per_trade = self.risk_limits.max_risk_per_trade
```

Replace the hardcoded `base_multiplier=2.0` on line 161 with `base_sl`.
Replace `risk_reward=2.5` on line 193 with `rr_ratio`.
Use `max_positions` for the position count check.
Use `risk_per_trade` for the sizing calculation.

**Step 2: Adjust dynamic multiplier range in stop_manager.py**

In `dynamic_multiplier()`, lines 14-15, make the min/max bounds configurable through parameters (they're already params with defaults, just need to be passed differently from risk_manager):

When scalp mode: call with `min_multiplier=0.7, max_multiplier=2.0` instead of defaults `1.5, 4.0`.

**Step 3: Run risk tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/risk/ -v --tb=short -x 2>&1 | tail -20
```

Expected: All pass (scalp defaults are off, so existing behavior preserved).

**Step 4: Commit**

```bash
git add backend/src/risk/risk_manager.py backend/src/risk/stop_manager.py
git commit -m "feat: adjust risk parameters for scalp mode (SL 1.0 ATR, TP 2.0 RR)"
```

---

### Task 6: Feed Extra Indicators into market_data

**Files:**
- Modify: `backend/src/trading/paper_loop.py` (around `_process_epic`, line 906-910)
- Modify: `backend/src/models/prediction_service.py` (`get_market_data()`)

**Goal:** The `market_data` dict passed to `StrategyManager.process_prediction()` must include the extra indicators that `ScalpScoreStrategy` needs: `ema_9`, `ema_21`, `macd_histogram`, `macd`, `macd_signal`, `volume`, `volume_sma_20`, `bb_upper`, `bb_lower`, `bb_middle`, `keltner_upper`, `keltner_lower`.

Currently `get_market_data()` only returns: `current_price`, `atr`, `rsi`, `regime`, `adx`.

**Step 1: Check what PredictionService.get_market_data() returns and extend it**

The method likely builds the features DataFrame and extracts a few fields. We need to extract the additional indicator values from the last row of the features DataFrame.

Add to the return dict in `get_market_data()`:
```python
# After existing extractions:
result["ema_9"] = float(last_row.get("ema_9", 0))
result["ema_21"] = float(last_row.get("ema_21", 0))
result["macd_histogram"] = float(last_row.get("macd_histogram", 0))
result["macd"] = float(last_row.get("macd", 0))
result["macd_signal"] = float(last_row.get("macd_signal", 0))
result["volume"] = float(last_row.get("volume", 0))
result["volume_sma_20"] = float(last_row.get("volume_sma_20", 0))
result["bb_upper"] = float(last_row.get("bb_upper", 0))
result["bb_lower"] = float(last_row.get("bb_lower", 0))
result["bb_middle"] = float(last_row.get("bb_middle", 0))
result["keltner_upper"] = float(last_row.get("keltner_upper", 0))
result["keltner_lower"] = float(last_row.get("keltner_lower", 0))
```

**Step 2: Run prediction service tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/models/ -v --tb=short -x 2>&1 | tail -20
```

**Step 3: Commit**

```bash
git add backend/src/models/prediction_service.py
git commit -m "feat: expose extra technical indicators in market_data for scalp strategy"
```

---

### Task 7: Wire Scalp Mode in App Startup

**Files:**
- Modify: `backend/src/api/main.py` or `backend/src/api/dependencies.py` (where StrategyManager is created)

**Step 1: Pass scalp_mode flag when creating StrategyManager**

Find where `StrategyManager.from_optimal_thresholds()` is called during startup and add:

```python
settings = get_settings()
strategy_manager = StrategyManager.from_optimal_thresholds()
strategy_manager.scalp_mode = settings.scalp_mode_enabled
if settings.scalp_mode_enabled:
    from src.strategy.scalp_score_strategy import ScalpScoreStrategy
    strategy_manager._scalp_strategy = ScalpScoreStrategy(
        entry_threshold=settings.scalp_score_threshold,
        full_size_threshold=settings.scalp_score_full_threshold,
    )
    logger.info("Scalp mode ENABLED — using ScalpScoreStrategy as primary signal")
```

**Step 2: Also update circuit breaker consecutive losses threshold**

When scalp mode is enabled, set stricter CB:
```python
if settings.scalp_mode_enabled:
    risk_manager.circuit_breakers.config.max_consecutive_losses = 4
```

**Step 3: Verify app starts**

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
sleep 15
curl -s http://localhost:8000/api/trading/status | python -m json.tool | grep -E "execution_mode|running"
```

**Step 4: Commit**

```bash
git add backend/src/api/main.py backend/src/api/dependencies.py
git commit -m "feat: wire scalp mode into app startup with configurable thresholds"
```

---

### Task 8: Run Full Test Suite + Integration Verification

**Step 1: Run all tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short -x 2>&1 | tail -40
```

Expected: All ~1199 tests pass. Any failures MUST be fixed before proceeding.

**Step 2: Verify trading loop works with scalp mode**

```bash
curl -s -X POST http://localhost:8000/api/trading/start | python -m json.tool | grep -E "execution_mode|running|interval"
```

Check logs for scalp-mode signals:
```bash
tail -50 backend/logs/algotrader_*.log | grep -i "scalp\|ScalpScore"
```

**Step 3: Commit if any fixes needed**

```bash
git add -A && git commit -m "fix: address test failures from scalp mode integration"
```

---

### Task 9: Final — Push Branch and Summary

**Step 1: Push feature branch**

```bash
git push -u origin feature/scalp-hybrid-strategy
```

**Step 2: Verify all commits**

```bash
git log --oneline master..feature/scalp-hybrid-strategy
```

Expected: 7-8 clean commits with conventional commit messages.

---

## Execution Dependency Graph

```
Task 1 (config) ──┐
                   ├── Task 2 (ScalpScoreStrategy) ──┐
                   │                                   ├── Task 3 (StrategyManager wiring)
                   │                                   │
Task 4 (paper_loop) ──────────────────────────────────┤
Task 5 (risk params) ─────────────────────────────────┤
Task 6 (market_data indicators) ──────────────────────┤
                                                       ├── Task 7 (app startup wiring)
                                                       └── Task 8 (full test suite)
                                                            └── Task 9 (push)
```

Tasks 1-2 are sequential (2 depends on 1).
Tasks 4, 5, 6 can run in parallel after Task 1.
Task 3 depends on Task 2.
Task 7 depends on Tasks 3, 4, 5, 6.
Task 8 depends on Task 7.
