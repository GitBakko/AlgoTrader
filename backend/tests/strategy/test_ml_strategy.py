"""Tests for MLStrategy class."""

from unittest.mock import patch

import polars as pl
import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.ml_strategy import MLStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal


def _make_prediction(
    signal_class: int = SignalClass.BUY, confidence: float = 0.65
) -> PredictionResult:
    """Helper to create a PredictionResult for testing."""
    return PredictionResult(
        signal_class=signal_class,
        signal_name=SignalClass(signal_class).name,
        confidence=confidence,
        probabilities={"SELL": 0.10, "HOLD": 0.25, "BUY": confidence},
    )


def _make_hold_signal(epic: str, price: float) -> TradingSignal:
    """Helper to create a HOLD TradingSignal returned by the mocked SignalGenerator."""
    return TradingSignal(
        epic=epic,
        direction=SignalDirection.HOLD,
        confidence=0.0,
        signal_class=SignalClass.HOLD,
        entry_price=price,
        technical_confirmation=False,
    )


def _make_buy_signal(epic: str, price: float, confidence: float) -> TradingSignal:
    """Helper to create a BUY TradingSignal returned by the mocked SignalGenerator."""
    return TradingSignal(
        epic=epic,
        direction=SignalDirection.BUY,
        confidence=confidence,
        signal_class=SignalClass.BUY,
        entry_price=price,
        technical_confirmation=True,
        suggested_stop=price - 40.0,
        suggested_tp=price + 80.0,
    )


class TestMLStrategyProperties:
    """Tests for MLStrategy name and applicable_regimes properties."""

    def test_name_returns_ml_ensemble(self):
        strategy = MLStrategy()
        assert strategy.name == "ml_ensemble"

    def test_applicable_regimes(self):
        strategy = MLStrategy()
        regimes = strategy.applicable_regimes
        assert regimes == ["trending_up", "trending_down", "ranging"]
        assert len(regimes) == 3


class TestMLStrategyGenerateSignal:
    """Tests for MLStrategy.generate_signal (real-time signal generation)."""

    def setup_method(self):
        self.strategy = MLStrategy()
        self.config = StrategyConfig()
        self.recent_bars = pl.DataFrame({"close": [100.0, 101.0, 102.0]})

    def test_no_prediction_returns_hold(self):
        """When current_bar has no 'prediction' key, returns HOLD."""
        current_bar = {"close": 2000.0}
        signal = self.strategy.generate_signal(
            "GOLD", current_bar, self.recent_bars, self.config
        )
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.0
        assert signal.signal_class == SignalClass.HOLD
        assert signal.entry_price == 2000.0
        assert signal.technical_confirmation is False
        assert signal.strategy_name == "ml_ensemble"

    def test_prediction_none_returns_hold(self):
        """When prediction is explicitly None, returns HOLD."""
        current_bar = {"close": 2000.0, "prediction": None}
        signal = self.strategy.generate_signal(
            "GOLD", current_bar, self.recent_bars, self.config
        )
        assert signal.direction == SignalDirection.HOLD
        assert signal.strategy_name == "ml_ensemble"

    def test_price_zero_returns_hold(self):
        """When close price is 0, returns HOLD even if prediction exists."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        current_bar = {"close": 0, "prediction": pred}
        signal = self.strategy.generate_signal(
            "GOLD", current_bar, self.recent_bars, self.config
        )
        assert signal.direction == SignalDirection.HOLD
        assert signal.entry_price == 0.0

    def test_price_negative_returns_hold(self):
        """When close price is negative, returns HOLD."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        current_bar = {"close": -10.0, "prediction": pred}
        signal = self.strategy.generate_signal(
            "GOLD", current_bar, self.recent_bars, self.config
        )
        assert signal.direction == SignalDirection.HOLD

    def test_missing_close_returns_hold(self):
        """When close key is missing, price defaults to 0 -> HOLD."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        current_bar = {"prediction": pred}
        signal = self.strategy.generate_signal(
            "GOLD", current_bar, self.recent_bars, self.config
        )
        assert signal.direction == SignalDirection.HOLD
        assert signal.entry_price == 0.0

    @patch("src.strategy.ml_strategy.SignalGenerator.generate_signal")
    def test_valid_prediction_calls_signal_generator(self, mock_sg):
        """With valid prediction and price, delegates to SignalGenerator."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        mock_sg.return_value = _make_buy_signal("GOLD", 2000.0, 0.65)

        current_bar = {
            "close": 2000.0,
            "prediction": pred,
            "atr_14": 20.0,
            "rsi_14": 55.0,
            "adx": 30.0,
            "regime": "trending_up",
        }
        signal = self.strategy.generate_signal(
            "GOLD", current_bar, self.recent_bars, self.config
        )

        mock_sg.assert_called_once_with(
            prediction=pred,
            epic="GOLD",
            current_price=2000.0,
            atr=20.0,
            rsi=55.0,
            regime="trending_up",
            config=self.config,
            adx=30.0,
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.strategy_name == "ml_ensemble"

    @patch("src.strategy.ml_strategy.SignalGenerator.generate_signal")
    def test_atr_defaults_to_1_percent_of_price(self, mock_sg):
        """When atr_14 is missing, defaults to price * 0.01."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        mock_sg.return_value = _make_buy_signal("GOLD", 2000.0, 0.65)

        current_bar = {"close": 2000.0, "prediction": pred}
        self.strategy.generate_signal("GOLD", current_bar, self.recent_bars, self.config)

        call_kwargs = mock_sg.call_args.kwargs
        assert call_kwargs["atr"] == pytest.approx(20.0)  # 2000 * 0.01
        assert call_kwargs["rsi"] is None
        assert call_kwargs["adx"] is None
        assert call_kwargs["regime"] is None

    @patch("src.strategy.ml_strategy.SignalGenerator.generate_signal")
    def test_rsi_and_adx_converted_to_float(self, mock_sg):
        """rsi_14 and adx values are converted to float."""
        pred = _make_prediction(SignalClass.SELL, 0.70)
        mock_sg.return_value = _make_hold_signal("GOLD", 2000.0)

        current_bar = {
            "close": 2000.0,
            "prediction": pred,
            "atr_14": 20,
            "rsi_14": 45,  # int, should become float
            "adx": 28,  # int, should become float
        }
        self.strategy.generate_signal("GOLD", current_bar, self.recent_bars, self.config)

        call_kwargs = mock_sg.call_args.kwargs
        assert isinstance(call_kwargs["rsi"], float)
        assert call_kwargs["rsi"] == 45.0
        assert isinstance(call_kwargs["adx"], float)
        assert call_kwargs["adx"] == 28.0

    @patch("src.strategy.ml_strategy.SignalGenerator.generate_signal")
    def test_strategy_name_tagged_on_returned_signal(self, mock_sg):
        """The returned signal always has strategy_name='ml_ensemble'."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        returned_signal = _make_buy_signal("GOLD", 2000.0, 0.65)
        returned_signal.strategy_name = None  # SignalGenerator doesn't set it
        mock_sg.return_value = returned_signal

        current_bar = {"close": 2000.0, "prediction": pred, "atr_14": 20.0}
        signal = self.strategy.generate_signal(
            "GOLD", current_bar, self.recent_bars, self.config
        )
        assert signal.strategy_name == "ml_ensemble"


class TestMLStrategyGenerateBacktestSignals:
    """Tests for MLStrategy.generate_backtest_signals (batch backtest mode)."""

    def setup_method(self):
        self.strategy = MLStrategy()

    def test_missing_signal_class_column_returns_zeros(self):
        """If signal_class column is absent, returns signal_direction=0, signal_confidence=0."""
        df = pl.DataFrame({
            "timestamp": [1, 2, 3],
            "close": [100.0, 101.0, 102.0],
        })
        result = self.strategy.generate_backtest_signals(df, "GOLD", "1h")

        assert "signal_direction" in result.columns
        assert "signal_confidence" in result.columns
        assert result["signal_direction"].to_list() == [0, 0, 0]
        assert result["signal_confidence"].to_list() == [0.0, 0.0, 0.0]

    def test_missing_confidence_column_returns_zeros(self):
        """If confidence column is absent (but signal_class present), returns zeros."""
        df = pl.DataFrame({
            "timestamp": [1, 2, 3],
            "close": [100.0, 101.0, 102.0],
            "signal_class": [0, 1, 2],
        })
        result = self.strategy.generate_backtest_signals(df, "GOLD", "1h")

        assert result["signal_direction"].to_list() == [0, 0, 0]
        assert result["signal_confidence"].to_list() == [0.0, 0.0, 0.0]

    def test_buy_mapped_to_direction_1(self):
        """SignalClass.BUY (2) maps to signal_direction=1."""
        df = pl.DataFrame({
            "close": [100.0],
            "signal_class": [SignalClass.BUY],
            "confidence": [0.70],
        })
        result = self.strategy.generate_backtest_signals(df, "GOLD", "1h")
        assert result["signal_direction"].to_list() == [1]
        assert result["signal_confidence"].to_list() == [0.70]

    def test_sell_mapped_to_direction_minus1(self):
        """SignalClass.SELL (0) maps to signal_direction=-1."""
        df = pl.DataFrame({
            "close": [100.0],
            "signal_class": [SignalClass.SELL],
            "confidence": [0.60],
        })
        result = self.strategy.generate_backtest_signals(df, "GOLD", "1h")
        assert result["signal_direction"].to_list() == [-1]
        assert result["signal_confidence"].to_list() == [0.60]

    def test_hold_mapped_to_direction_0(self):
        """SignalClass.HOLD (1) maps to signal_direction=0."""
        df = pl.DataFrame({
            "close": [100.0],
            "signal_class": [SignalClass.HOLD],
            "confidence": [0.55],
        })
        result = self.strategy.generate_backtest_signals(df, "GOLD", "1h")
        assert result["signal_direction"].to_list() == [0]
        assert result["signal_confidence"].to_list() == [0.55]

    def test_mixed_signals_mapped_correctly(self):
        """Multiple rows with different signal classes are mapped correctly."""
        df = pl.DataFrame({
            "close": [100.0, 101.0, 102.0, 103.0],
            "signal_class": [
                SignalClass.SELL,
                SignalClass.HOLD,
                SignalClass.BUY,
                SignalClass.HOLD,
            ],
            "confidence": [0.60, 0.55, 0.80, 0.45],
        })
        result = self.strategy.generate_backtest_signals(df, "GOLD", "1h")
        assert result["signal_direction"].to_list() == [-1, 0, 1, 0]
        assert result["signal_confidence"].to_list() == [0.60, 0.55, 0.80, 0.45]

    def test_original_df_not_mutated(self):
        """generate_backtest_signals should not mutate the input DataFrame."""
        df = pl.DataFrame({
            "close": [100.0],
            "signal_class": [SignalClass.BUY],
            "confidence": [0.70],
        })
        original_columns = df.columns.copy()
        self.strategy.generate_backtest_signals(df, "GOLD", "1h")
        assert df.columns == original_columns
        assert "signal_direction" not in df.columns
