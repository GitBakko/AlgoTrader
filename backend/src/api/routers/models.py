"""
Models API router.
Provides ML model information, performance metrics, and version history.
Dual-mode: uses ModelVersioning from filesystem when available, falls back to static registry.
"""

from fastapi import APIRouter, Depends, Path

from src.api.dependencies import get_model_versioning, get_prediction_service
from src.api.schemas import error_response, success_response

router = APIRouter()

# Static fallback registry (used when no ModelVersioning or no saved models)
_MODEL_REGISTRY = [
    {
        "id": "xgboost-xauusd-v1", "name": "XGBoost Gold", "type": "xgboost",
        "epic": "XAUUSD", "status": "active",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-btcusd-v1", "name": "XGBoost Bitcoin", "type": "xgboost",
        "epic": "BTCUSD", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-us500-v1", "name": "XGBoost S&P 500", "type": "xgboost",
        "epic": "US500", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-wtiusd-v1", "name": "XGBoost Crude Oil", "type": "xgboost",
        "epic": "WTIUSD", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-eurusd-v1", "name": "XGBoost EUR/USD", "type": "xgboost",
        "epic": "EURUSD", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-nvda-v1", "name": "XGBoost NVIDIA", "type": "xgboost",
        "epic": "NVDA", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-tsla-v1", "name": "XGBoost Tesla", "type": "xgboost",
        "epic": "TSLA", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-xagusd-v1", "name": "XGBoost Silver", "type": "xgboost",
        "epic": "XAGUSD", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
    {
        "id": "xgboost-de40-v1", "name": "XGBoost DAX", "type": "xgboost",
        "epic": "DE40", "status": "untrained",
        "accuracy": 0.0, "f1_score": 0.0, "last_trained": None, "version": "1.0.0",
    },
]

_MODEL_MAP = {m["id"]: m for m in _MODEL_REGISTRY}


def _metadata_to_dict(meta, prediction_service=None) -> dict:
    """Convert ModelMetadata to API response dict."""
    status = "trained"
    if prediction_service and prediction_service.has_model_for(meta.epic):
        status = "active"

    accuracy = 0.0
    f1_score = 0.0
    if meta.training_result and meta.training_result.avg_test_metrics:
        accuracy = meta.training_result.avg_test_metrics.get("accuracy", 0.0)
        f1_score = meta.training_result.avg_test_metrics.get("f1_macro", 0.0)

    return {
        "id": meta.model_id,
        "name": f"{meta.model_type.title()} {meta.epic}",
        "type": meta.model_type,
        "epic": meta.epic,
        "status": status,
        "accuracy": accuracy,
        "f1_score": f1_score,
        "last_trained": meta.created_at.isoformat() if meta.created_at else None,
        "version": str(meta.version),
    }


@router.get("/")
async def list_models(
    model_versioning=Depends(get_model_versioning),
    prediction_service=Depends(get_prediction_service),
):
    """List all registered ML models."""
    if model_versioning is not None:
        all_metadata = model_versioning.list_models()
        if all_metadata:
            return success_response([
                _metadata_to_dict(m, prediction_service) for m in all_metadata
            ])

    return success_response(_MODEL_REGISTRY)


@router.get("/{model_id}/metrics")
async def get_model_metrics(
    model_id: str = Path(...),
    model_versioning=Depends(get_model_versioning),
):
    """Get detailed performance metrics for a model."""
    if model_versioning is not None:
        all_metadata = model_versioning.list_models()
        meta = next((m for m in all_metadata if m.model_id == model_id), None)
        if meta is not None:
            metrics = {"model_id": model_id, "accuracy": 0.0, "f1_score": 0.0,
                       "precision": 0.0, "recall": 0.0,
                       "confusion_matrix": None, "class_report": None}
            if meta.training_result and meta.training_result.avg_test_metrics:
                tm = meta.training_result.avg_test_metrics
                metrics["accuracy"] = tm.get("accuracy", 0.0)
                metrics["f1_score"] = tm.get("f1_macro", 0.0)
                metrics["precision"] = tm.get("precision_macro", 0.0)
                metrics["recall"] = tm.get("recall_macro", 0.0)
            return success_response(metrics)

    # Fallback: static registry
    model = _MODEL_MAP.get(model_id)
    if model is None:
        return error_response(f"Model {model_id} not found", 404)

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
async def get_model_versions(
    model_id: str = Path(...),
    model_versioning=Depends(get_model_versioning),
):
    """Get version history for a model."""
    if model_versioning is not None:
        all_metadata = model_versioning.list_models()
        meta = next((m for m in all_metadata if m.model_id == model_id), None)
        if meta is not None:
            metrics = {"accuracy": 0.0, "f1_score": 0.0}
            if meta.training_result and meta.training_result.avg_test_metrics:
                tm = meta.training_result.avg_test_metrics
                metrics["accuracy"] = tm.get("accuracy", 0.0)
                metrics["f1_score"] = tm.get("f1_macro", 0.0)
            return success_response([{
                "version": str(meta.version),
                "created_at": meta.created_at.isoformat() if meta.created_at else None,
                "status": "trained",
                "metrics": metrics,
            }])

    # Fallback: static registry
    model = _MODEL_MAP.get(model_id)
    if model is None:
        return error_response(f"Model {model_id} not found", 404)

    versions = [
        {
            "version": model["version"],
            "created_at": model["last_trained"],
            "status": model["status"],
            "metrics": {"accuracy": model["accuracy"], "f1_score": model["f1_score"]},
        }
    ]

    return success_response(versions)
