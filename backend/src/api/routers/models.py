"""
Models API router.
Provides ML model information, performance metrics, and version history.
"""

from fastapi import APIRouter, Path

from src.api.schemas import error_response, success_response

router = APIRouter()

# MVP: static model registry (actual models from versioning system in Phase 5)
_MODEL_REGISTRY = [
    {
        "id": "xgboost-xauusd-v1",
        "name": "XGBoost Gold",
        "type": "xgboost",
        "epic": "XAUUSD",
        "status": "active",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-btcusd-v1",
        "name": "XGBoost Bitcoin",
        "type": "xgboost",
        "epic": "BTCUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-us500-v1",
        "name": "XGBoost S&P 500",
        "type": "xgboost",
        "epic": "US500",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
]

_MODEL_MAP = {m["id"]: m for m in _MODEL_REGISTRY}


@router.get("/")
async def list_models():
    """List all registered ML models."""
    return success_response(_MODEL_REGISTRY)


@router.get("/{model_id}/metrics")
async def get_model_metrics(model_id: str = Path(...)):
    """Get detailed performance metrics for a model."""
    model = _MODEL_MAP.get(model_id)
    if model is None:
        return error_response(f"Model {model_id} not found", 404)

    # MVP: return basic structure (actual metrics from evaluator in Phase 5)
    metrics = {
        "model_id": model_id,
        "accuracy": model["accuracy"],
        "f1_score": model["f1_score"],
        "precision": 0.0,
        "recall": 0.0,
        "confusion_matrix": None,
        "class_report": None,
    }

    return success_response(metrics)


@router.get("/{model_id}/versions")
async def get_model_versions(model_id: str = Path(...)):
    """Get version history for a model."""
    model = _MODEL_MAP.get(model_id)
    if model is None:
        return error_response(f"Model {model_id} not found", 404)

    # MVP: single version
    versions = [
        {
            "version": model["version"],
            "created_at": model["last_trained"],
            "status": model["status"],
            "metrics": {"accuracy": model["accuracy"], "f1_score": model["f1_score"]},
        }
    ]

    return success_response(versions)
