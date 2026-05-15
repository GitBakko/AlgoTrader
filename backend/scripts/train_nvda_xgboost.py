"""Quick training script for NVDA XGBoost with sentiment."""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime
from loguru import logger

from src.models.xgboost_model import XGBoostClassifier
from src.models.trainer import ModelTrainer
from src.models.versioning import ModelVersioning


def main():
    logger.info("=" * 60)
    logger.info("Training NVDA XGBoost with Sentiment Features")
    logger.info("=" * 60)

    # Initialize
    trainer = ModelTrainer()
    versioning = ModelVersioning()

    # Create model
    model = XGBoostClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05
    )

    # Train with sentiment
    logger.info("[TRAIN] Starting training...")
    result = trainer.train(
        model=model,
        epic="NVDA",
        timeframe="1h",
        save_best=False,
        multi_timeframe=True,
        include_sentiment=True,
    )

    logger.info(f"\n[RESULTS] Training Complete!")
    logger.info(f"F1 Macro:    {result.avg_test_metrics.get('f1_macro', 0.0):.4f}")
    logger.info(f"Accuracy:    {result.avg_test_metrics.get('accuracy', 0.0):.4f}")
    logger.info(f"Num Features: {result.num_features}")
    logger.info(f"Num Folds:   {len(result.fold_results)}")
    logger.info(f"Best Fold:   {result.best_fold_index} (F1={result.fold_results[result.best_fold_index].test_f1:.4f if result.best_fold_index is not None else 'N/A'})")

    # Save model
    model_dir = versioning.save_model(
        model=model,
        epic="NVDA",
        timeframe="1h",
        metadata={
            "f1_macro": result.avg_test_metrics.get('f1_macro', 0.0),
            "accuracy": result.avg_test_metrics.get('accuracy', 0.0),
            "num_features": result.num_features,
            "num_folds": len(result.fold_results),
            "best_fold": result.best_fold_index,
            "sentiment_enabled": True,
        },
    )

    logger.info(f"\n[SAVED] Model saved to: {model_dir}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
