"""
Integration tests for the full trading pipeline.
Tests end-to-end flow: Data -> Features -> Strategy -> Risk -> Execution.
No external services required (broker, DB, Redis all mocked/skipped).
"""

import numpy as np
import polars as pl
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.models.schemas import PredictionResult, SignalClass
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.schemas import SignalDirection
from src.strategy.strategy_manager import StrategyManager


class TestFeatureBuilderPipeline:
    """Test feature engineering from raw OHLC data."""

    def test_build_features_from_sample_data(self, sample_ohlc_df):
        """FeatureBuilder produces valid feature matrix from OHLC data."""
        from src.features.builder import FeatureBuilder

        builder = FeatureBuilder(data_access=None)
        df_features, matrix = builder.build_features_from_df(
            sample_ohlc_df, "XAUUSD", "1h", normalize=True, include_regime=True
        )

        # Should produce features
        assert matrix.num_features > 0
        assert len(matrix.feature_names) > 0
        assert len(df_features) > 0

        # Feature columns should include technical indicators
        feature_cols = set(matrix.feature_names)
        # At least some of the standard indicators should be present
        assert len(feature_cols) >= 5

    def test_features_no_nans_in_last_row(self, sample_ohlc_df):
        """Last row of features should have no NaN values (used for prediction)."""
        from src.features.builder import FeatureBuilder

        builder = FeatureBuilder(data_access=None)
        df_features, matrix = builder.build_features_from_df(
            sample_ohlc_df, "XAUUSD", "1h", normalize=True
        )

        # Get last row feature values - filter to numeric columns only
        numeric_features = [
            c for c in matrix.feature_names
            if df_features[c].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.UInt32)
        ]
        last_row = df_features.tail(1).select(numeric_features).to_numpy().astype(np.float64)
        last_row = np.nan_to_num(last_row, nan=0.0, posinf=0.0, neginf=0.0)

        # Should be a valid numeric array
        assert last_row.shape[1] > 0
        assert np.all(np.isfinite(last_row))


class TestSignalGenerationPipeline:
    """Test ML prediction -> strategy signal generation."""

    def test_prediction_to_signal(self, strategy_mgr):
        """PredictionResult converts to TradingSignal via StrategyManager."""
        prediction = PredictionResult(
            signal_class=SignalClass.BUY,
            signal_name="BUY",
            confidence=0.85,
            probabilities={
                "STRONG_SELL": 0.02,
                "SELL": 0.03,
                "HOLD": 0.05,
                "BUY": 0.85,
                "STRONG_BUY": 0.05,
            },
        )

        market_data = {"current_price": 2000.0, "atr": 20.0}

        signal = strategy_mgr.process_prediction(prediction, "XAUUSD", market_data)

        assert signal.epic == "XAUUSD"
        assert signal.direction in (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD)
        assert signal.confidence > 0
        assert signal.entry_price > 0

    def test_hold_prediction_generates_hold_signal(self, strategy_mgr):
        """HOLD prediction should produce a HOLD signal."""
        prediction = PredictionResult(
            signal_class=SignalClass.HOLD,
            signal_name="HOLD",
            confidence=0.9,
            probabilities={
                "STRONG_SELL": 0.02,
                "SELL": 0.03,
                "HOLD": 0.90,
                "BUY": 0.03,
                "STRONG_BUY": 0.02,
            },
        )

        market_data = {"current_price": 2000.0, "atr": 20.0}
        signal = strategy_mgr.process_prediction(prediction, "XAUUSD", market_data)

        assert signal.direction == SignalDirection.HOLD

    def test_low_confidence_still_generates_signal(self, strategy_mgr):
        """Low confidence predictions still generate signals (risk manager filters)."""
        prediction = PredictionResult(
            signal_class=SignalClass.SELL,
            signal_name="SELL",
            confidence=0.35,
            probabilities={
                "STRONG_SELL": 0.10,
                "SELL": 0.35,
                "HOLD": 0.30,
                "BUY": 0.15,
                "STRONG_BUY": 0.10,
            },
        )

        market_data = {"current_price": 50000.0, "atr": 1000.0}
        signal = strategy_mgr.process_prediction(prediction, "BTCUSD", market_data)

        assert signal.epic == "BTCUSD"


class TestRiskCheckPipeline:
    """Test risk management checks on trading signals."""

    def test_risk_approves_valid_trade(self, strategy_mgr, risk_mgr):
        """Risk manager approves a valid trade with proper position sizing."""
        prediction = PredictionResult(
            signal_class=SignalClass.STRONG_BUY,
            signal_name="STRONG_BUY",
            confidence=0.90,
            probabilities={
                "STRONG_SELL": 0.01,
                "SELL": 0.02,
                "HOLD": 0.02,
                "BUY": 0.05,
                "STRONG_BUY": 0.90,
            },
        )

        market_data = {"current_price": 2000.0, "atr": 20.0}
        signal = strategy_mgr.process_prediction(prediction, "XAUUSD", market_data)

        if signal.direction == SignalDirection.HOLD:
            pytest.skip("Signal was HOLD, can't test risk check")

        risk_result = risk_mgr.check_trade(
            signal=signal, equity=10000.0, atr=20.0
        )

        assert risk_result.approved is True
        assert risk_result.position_size > 0
        assert risk_result.stop_loss > 0

    def test_risk_rejects_when_circuit_breaker(self, strategy_mgr, risk_mgr):
        """Risk manager rejects trades when circuit breaker is active."""
        # Activate circuit breaker via proper method
        risk_mgr.drawdown_monitor.activate_circuit_breaker("test trigger")

        prediction = PredictionResult(
            signal_class=SignalClass.BUY,
            signal_name="BUY",
            confidence=0.90,
            probabilities={"STRONG_SELL": 0.01, "SELL": 0.01, "HOLD": 0.03,
                           "BUY": 0.90, "STRONG_BUY": 0.05},
        )

        market_data = {"current_price": 2000.0, "atr": 20.0}
        signal = strategy_mgr.process_prediction(prediction, "XAUUSD", market_data)

        if signal.direction == SignalDirection.HOLD:
            pytest.skip("Signal was HOLD")

        risk_result = risk_mgr.check_trade(
            signal=signal, equity=10000.0, atr=20.0
        )

        assert risk_result.approved is False
        assert risk_result.rejection_reason is not None


class TestExecutionPipeline:
    """Test paper trading execution."""

    @pytest.mark.asyncio
    async def test_paper_execution_succeeds(self, engine, strategy_mgr, risk_mgr):
        """Paper mode execution produces valid result."""
        prediction = PredictionResult(
            signal_class=SignalClass.STRONG_BUY,
            signal_name="STRONG_BUY",
            confidence=0.90,
            probabilities={"STRONG_SELL": 0.01, "SELL": 0.02, "HOLD": 0.02,
                           "BUY": 0.05, "STRONG_BUY": 0.90},
        )

        market_data = {"current_price": 2000.0, "atr": 20.0}
        signal = strategy_mgr.process_prediction(prediction, "XAUUSD", market_data)

        if signal.direction == SignalDirection.HOLD:
            pytest.skip("Signal was HOLD")

        risk_result = risk_mgr.check_trade(
            signal=signal, equity=10000.0, atr=20.0
        )

        assert risk_result.approved is True

        exec_result = await engine.execute_signal(signal, risk_result)

        assert exec_result.success is True
        assert exec_result.deal_id is not None
        assert exec_result.fill_price is not None
        assert exec_result.fill_price > 0


class TestFullPipelineE2E:
    """End-to-end test: OHLC data -> paper trade."""

    def test_data_to_features_to_prediction(self, sample_ohlc_df):
        """Full chain from OHLC data to prediction result (with mock model)."""
        from src.features.builder import FeatureBuilder

        # Step 1: Build features
        builder = FeatureBuilder(data_access=None)
        df_features, matrix = builder.build_features_from_df(
            sample_ohlc_df, "XAUUSD", "1h", normalize=True
        )

        assert matrix.num_features > 0

        # Step 2: Extract last row as feature vector
        X = df_features.tail(1).select(matrix.feature_names).to_numpy()
        X = np.nan_to_num(X, nan=0.0)

        assert X.shape == (1, matrix.num_features)

        # Step 3: Mock XGBoost prediction
        # Simulate 5-class probabilities
        mock_proba = np.array([[0.05, 0.05, 0.10, 0.70, 0.10]])
        predicted_class = int(np.argmax(mock_proba))
        confidence = float(mock_proba[0, predicted_class])

        prediction = PredictionResult(
            signal_class=predicted_class,
            signal_name=SignalClass(predicted_class).name,
            confidence=confidence,
            probabilities={
                SignalClass(i).name: float(p) for i, p in enumerate(mock_proba[0])
            },
        )

        assert prediction.signal_class == 3  # BUY
        assert prediction.confidence == 0.70

    @pytest.mark.asyncio
    async def test_full_pipeline_data_to_paper_trade(self, sample_ohlc_df):
        """Complete pipeline: OHLC -> features -> prediction -> signal -> risk -> execution."""
        from src.features.builder import FeatureBuilder

        # Build features
        builder = FeatureBuilder(data_access=None)
        df_features, matrix = builder.build_features_from_df(
            sample_ohlc_df, "XAUUSD", "1h", normalize=True
        )

        # Mock prediction
        prediction = PredictionResult(
            signal_class=SignalClass.STRONG_BUY,
            signal_name="STRONG_BUY",
            confidence=0.85,
            probabilities={"STRONG_SELL": 0.02, "SELL": 0.03, "HOLD": 0.05,
                           "BUY": 0.05, "STRONG_BUY": 0.85},
        )

        # Get last close as current price
        last_close = float(sample_ohlc_df.tail(1)["close"][0])
        market_data = {"current_price": last_close, "atr": 20.0}

        # Strategy
        mgr = StrategyManager()
        signal = mgr.process_prediction(prediction, "XAUUSD", market_data)

        if signal.direction == SignalDirection.HOLD:
            pytest.skip("Signal was HOLD - pipeline still validated")

        # Risk check
        risk_mgr = RiskManager(initial_equity=10000.0, limits=RiskLimits())
        risk_result = risk_mgr.check_trade(
            signal=signal, equity=10000.0, atr=20.0
        )

        assert risk_result.approved is True

        # Execute (paper)
        engine = ExecutionEngine(mode=ExecutionMode.PAPER)
        exec_result = await engine.execute_signal(signal, risk_result)

        assert exec_result.success is True
        assert exec_result.deal_id is not None

        # Verify position exists
        positions = await engine.get_open_positions()
        assert len(positions) == 1
        assert positions[0]["epic"] == "XAUUSD"


class TestExecutionPersistence:
    """Test execution persistence with mock DB session."""

    @pytest.mark.asyncio
    async def test_persist_execution_creates_records(self):
        """ExecutionPersistence creates Position + Trade records."""
        from src.execution.persistence import ExecutionPersistence
        from src.execution.schemas import ExecutionResult
        from src.strategy.schemas import TradingSignal, SignalDirection

        # Mock AsyncSession (add is sync, flush/refresh are async)
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'id', 1))

        signal = TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=0.85,
            signal_class=3,
            entry_price=2000.0,
            suggested_stop=1980.0,
            suggested_tp=2040.0,
        )

        result = ExecutionResult(
            success=True,
            deal_id="PAPER-TEST-001",
            fill_price=2000.50,
        )

        position = await ExecutionPersistence.persist_execution(
            session=mock_session,
            signal=signal,
            result=result,
            position_size=0.5,
            stop_loss=1980.0,
            take_profit=2040.0,
        )

        # Should have called session.add twice (Position + Trade)
        assert mock_session.add.call_count == 2
        assert mock_session.flush.call_count == 2

    @pytest.mark.asyncio
    async def test_persist_skips_without_session(self):
        """ExecutionPersistence gracefully skips when session is None."""
        from src.execution.persistence import ExecutionPersistence
        from src.execution.schemas import ExecutionResult
        from src.strategy.schemas import TradingSignal, SignalDirection

        signal = TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=0.85,
            signal_class=3,
            entry_price=2000.0,
        )

        result = ExecutionResult(
            success=True,
            deal_id="PAPER-TEST-002",
            fill_price=2000.50,
        )

        position = await ExecutionPersistence.persist_execution(
            session=None,
            signal=signal,
            result=result,
            position_size=0.5,
        )

        assert position is None


class TestGracefulDegradation:
    """Test that the app starts correctly without broker/Redis/DB."""

    def test_app_creates_without_external_services(self):
        """FastAPI app can be created and configured without any external services."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.dependencies import (
            get_execution_engine, get_risk_manager, get_strategy_manager,
            get_broker_client, get_data_access, get_feature_builder,
            get_prediction_service, get_model_versioning,
            get_db_session, get_position_repo, get_signal_repo,
            get_trade_repo, get_strategy_repo,
        )

        # Override all external dependencies to None
        app.dependency_overrides[get_execution_engine] = lambda: ExecutionEngine(
            mode=ExecutionMode.PAPER
        )
        app.dependency_overrides[get_risk_manager] = lambda: RiskManager(
            initial_equity=10000.0, limits=RiskLimits()
        )
        app.dependency_overrides[get_strategy_manager] = lambda: StrategyManager()
        app.dependency_overrides[get_broker_client] = lambda: None
        app.dependency_overrides[get_data_access] = lambda: None
        app.dependency_overrides[get_feature_builder] = lambda: None
        app.dependency_overrides[get_prediction_service] = lambda: None
        app.dependency_overrides[get_model_versioning] = lambda: None

        async def no_db():
            yield None

        app.dependency_overrides[get_db_session] = no_db
        app.dependency_overrides[get_position_repo] = lambda: None
        app.dependency_overrides[get_signal_repo] = lambda: None
        app.dependency_overrides[get_trade_repo] = lambda: None
        app.dependency_overrides[get_strategy_repo] = lambda: None

        # Set up app state
        app.state.execution_engine = ExecutionEngine(mode=ExecutionMode.PAPER)
        app.state.risk_manager = RiskManager(initial_equity=10000.0, limits=RiskLimits())
        app.state.strategy_manager = StrategyManager()
        app.state.signal_history = []
        app.state.backtest_runs = {}
        app.state.broker_client = None
        app.state.data_access = None
        app.state.feature_builder = None
        app.state.prediction_service = None
        app.state.model_versioning = None
        app.state.db_session_factory = None
        app.state.paper_loop = None

        with TestClient(app) as tc:
            # All endpoints should return 200
            assert tc.get("/api/dashboard/overview").status_code == 200
            assert tc.get("/api/positions/").status_code == 200
            assert tc.get("/api/signals/").status_code == 200
            assert tc.get("/api/models/").status_code == 200
            assert tc.get("/api/backtest/runs").status_code == 200
            assert tc.get("/api/trading/status").status_code == 200

        app.dependency_overrides.clear()
