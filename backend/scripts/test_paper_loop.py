"""
Quick test: runs a single paper trading iteration to verify the full pipeline.
ML prediction -> Strategy signal -> Risk check -> Paper execution

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/test_paper_loop.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.features.builder import FeatureBuilder
from src.models.prediction_service import PredictionService
from src.models.versioning import ModelVersioning
from src.risk.risk_manager import RiskManager
from src.strategy.strategy_manager import StrategyManager
from src.trading.paper_loop import PaperTradingLoop


async def main():
    logger.info("=" * 60)
    logger.info("Paper Trading Loop - Single Iteration Test")
    logger.info("=" * 60)

    # Initialize all services
    storage = ParquetStorageManager()
    data_access = DataAccessLayer(storage=storage)
    feature_builder = FeatureBuilder(data_access=data_access)
    versioning = ModelVersioning()

    prediction_service = PredictionService(
        feature_builder=feature_builder,
        model_versioning=versioning,
        data_access=data_access,
    )

    n_loaded = prediction_service.load_models()
    logger.info(f"Loaded {n_loaded} models")

    if n_loaded == 0:
        logger.error("No models found!")
        return

    strategy_manager = StrategyManager()
    risk_manager = RiskManager()

    execution_engine = ExecutionEngine(mode=ExecutionMode.PAPER)

    loop = PaperTradingLoop(
        prediction_service=prediction_service,
        strategy_manager=strategy_manager,
        risk_manager=risk_manager,
        execution_engine=execution_engine,
        interval_seconds=3600,
    )

    # Run a single iteration manually
    logger.info("\nRunning single iteration...")
    await loop._run_iteration()

    # Show status
    status = loop.get_status()
    logger.info(f"\n{'='*60}")
    logger.info("PAPER TRADING STATUS")
    logger.info(f"{'='*60}")
    logger.info(f"  Iterations: {status['iteration_count']}")
    logger.info(f"  Signals generated: {status['signal_count']}")
    logger.info(f"  Trades executed: {status['trade_count']}")
    logger.info(f"  Open positions: {status['open_positions']}")
    logger.info(f"  Total unrealized PnL: {status['total_unrealized_pnl']:.2f}")

    logger.info(f"\n  Last signals:")
    for epic, sig in status["last_signals"].items():
        logger.info(
            f"    {epic}: {sig['direction']} "
            f"@ {sig['entry_price']:.2f} "
            f"(conf={sig['confidence']:.2%})"
        )

    # Check results
    if status["signal_count"] > 0:
        logger.info("\nSUCCESS: Paper trading pipeline is working end-to-end!")
    else:
        logger.warning("\nWARNING: No signals were generated")

    if status["trade_count"] > 0:
        logger.info(f"  {status['trade_count']} trade(s) executed in paper mode")
    else:
        logger.info("  No trades executed (all signals filtered by confidence/risk)")


if __name__ == "__main__":
    asyncio.run(main())
