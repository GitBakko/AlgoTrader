"""
Models API router.
Provides ML model information, performance metrics, and version history.
Dual-mode: uses ModelVersioning from filesystem when available, falls back to static registry.
Also exposes extended data download endpoints for the Training Dashboard.
"""

import asyncio
import subprocess
import sys
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, Path, Query, Request
from loguru import logger

from src.api.dependencies import get_model_versioning, get_prediction_service
from src.api.schemas import error_response, success_response

router = APIRouter()

# Static fallback registry (used when no ModelVersioning or no saved models)
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
    {
        "id": "xgboost-wtiusd-v1",
        "name": "XGBoost Crude Oil",
        "type": "xgboost",
        "epic": "WTIUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-eurusd-v1",
        "name": "XGBoost EUR/USD",
        "type": "xgboost",
        "epic": "EURUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-nvda-v1",
        "name": "XGBoost NVIDIA",
        "type": "xgboost",
        "epic": "NVDA",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-tsla-v1",
        "name": "XGBoost Tesla",
        "type": "xgboost",
        "epic": "TSLA",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-xagusd-v1",
        "name": "XGBoost Silver",
        "type": "xgboost",
        "epic": "XAGUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-de40-v1",
        "name": "XGBoost DAX",
        "type": "xgboost",
        "epic": "DE40",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    # New 12 assets - Phase 12: Portfolio Expansion
    {
        "id": "xgboost-solusd-v1",
        "name": "XGBoost Solana",
        "type": "xgboost",
        "epic": "SOLUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-ethusd-v1",
        "name": "XGBoost Ethereum",
        "type": "xgboost",
        "epic": "ETHUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-bnbusd-v1",
        "name": "XGBoost Binance Coin",
        "type": "xgboost",
        "epic": "BNBUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-dogusd-v1",
        "name": "XGBoost Dogecoin",
        "type": "xgboost",
        "epic": "DOGUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-dashusd-v1",
        "name": "XGBoost Dash",
        "type": "xgboost",
        "epic": "DASHUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-icpusd-v1",
        "name": "XGBoost Internet Computer",
        "type": "xgboost",
        "epic": "ICPUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-natgas-v1",
        "name": "XGBoost Natural Gas",
        "type": "xgboost",
        "epic": "NATGAS",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-copper-v1",
        "name": "XGBoost Copper",
        "type": "xgboost",
        "epic": "COPPER",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-platinum-v1",
        "name": "XGBoost Platinum",
        "type": "xgboost",
        "epic": "PLATINUM",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-gbpusd-v1",
        "name": "XGBoost GBP/USD",
        "type": "xgboost",
        "epic": "GBPUSD",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-usdjpy-v1",
        "name": "XGBoost USD/JPY",
        "type": "xgboost",
        "epic": "USDJPY",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    {
        "id": "xgboost-nas100-v1",
        "name": "XGBoost Nasdaq 100",
        "type": "xgboost",
        "epic": "NAS100",
        "status": "untrained",
        "accuracy": 0.0,
        "f1_score": 0.0,
        "last_trained": None,
        "version": "1.0.0",
    },
    # Phase 14 stocks (2026-05-08)
    {"id": "xgboost-aapl-v1", "name": "XGBoost Apple", "type": "xgboost",
     "epic": "AAPL", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-msft-v1", "name": "XGBoost Microsoft", "type": "xgboost",
     "epic": "MSFT", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-googl-v1", "name": "XGBoost Alphabet", "type": "xgboost",
     "epic": "GOOGL", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-amzn-v1", "name": "XGBoost Amazon", "type": "xgboost",
     "epic": "AMZN", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-meta-v1", "name": "XGBoost Meta", "type": "xgboost",
     "epic": "META", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-amd-v1", "name": "XGBoost AMD", "type": "xgboost",
     "epic": "AMD", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    # Phase 14 forex (2026-05-08/09)
    {"id": "xgboost-usdchf-v1", "name": "XGBoost USD/CHF", "type": "xgboost",
     "epic": "USDCHF", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-usdcad-v1", "name": "XGBoost USD/CAD", "type": "xgboost",
     "epic": "USDCAD", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-audusd-v1", "name": "XGBoost AUD/USD", "type": "xgboost",
     "epic": "AUDUSD", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-nzdusd-v1", "name": "XGBoost NZD/USD", "type": "xgboost",
     "epic": "NZDUSD", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
    {"id": "xgboost-eurjpy-v1", "name": "XGBoost EUR/JPY", "type": "xgboost",
     "epic": "EURJPY", "status": "untrained", "accuracy": 0.0, "f1_score": 0.0,
     "last_trained": None, "version": "1.0.0"},
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
            return success_response(
                [_metadata_to_dict(m, prediction_service) for m in all_metadata]
            )

    return success_response(_MODEL_REGISTRY)


@router.get("/current")
async def get_current_models(
    prediction_service=Depends(get_prediction_service),
):
    """
    Currently-loaded models in the trading loop.

    Consumed by Dashboard v2 OperationalStrip tile #6 — shows a short
    banner like `ML-Primary · v2.3 · trained 2d ago`.

    Response:
      {
        "count": N,
        "by_epic": { epic: {model_id, model_type, version, last_trained, num_features} },
        "primary": { epic, model_id, model_type, version, last_trained } | None,
      }
    `primary` is the most recently created loaded model; useful as the
    single representative value for the operational-strip tile.
    """
    if prediction_service is None or not prediction_service.has_models:
        return success_response({"count": 0, "by_epic": {}, "primary": None})

    loaded = prediction_service.get_loaded_models()
    by_epic: dict[str, dict] = {}
    primary: dict | None = None
    for epic, info in loaded.items():
        entry = {
            "model_id":     info.get("model_id"),
            "model_type":   info.get("model_type"),
            "num_features": info.get("num_features"),
            "version":      info.get("version"),
            "last_trained": info.get("created_at"),
        }
        by_epic[epic] = entry
        # Pick the most-recently-created loaded model as the "primary".
        if primary is None or (
            entry["last_trained"] and entry["last_trained"] > (primary.get("last_trained") or "")
        ):
            primary = {"epic": epic, **entry}

    return success_response({
        "count": len(by_epic),
        "by_epic": by_epic,
        "primary": primary,
    })


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
            metrics = {
                "model_id": model_id,
                "accuracy": 0.0,
                "f1_score": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "confusion_matrix": None,
                "class_report": None,
            }
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
            return success_response(
                [
                    {
                        "version": str(meta.version),
                        "created_at": meta.created_at.isoformat() if meta.created_at else None,
                        "status": "trained",
                        "metrics": metrics,
                    }
                ]
            )

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


_VALID_EPICS = {m["epic"] for m in _MODEL_REGISTRY}


@router.post("/train/{epic}")
async def train_model(epic: str = Path(...)):
    """Trigger model training for a specific epic as a background subprocess."""
    if epic not in _VALID_EPICS:
        return error_response(f"Unknown epic: {epic}", 400)

    script = (
        FilePath(__file__).resolve().parent.parent.parent.parent / "scripts" / "train_models.py"
    )
    if not script.exists():
        return error_response("Training script not found", 500)

    # Ensure log directory exists
    log_dir = FilePath(__file__).resolve().parent.parent.parent.parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"train_{epic.lower()}.log"

    python = sys.executable

    subprocess.Popen(
        [python, str(script), "--assets", epic],
        cwd=str(script.parent.parent),
        stdout=log_file.open("w"),
        stderr=subprocess.STDOUT,
    )

    logger.info(f"Training subprocess started for {epic}")

    return success_response({"message": f"Training avviato per {epic}", "epic": epic})


@router.post("/retrain-all")
async def retrain_all(
    request: Request,
):
    """Trigger background retraining for all active assets via the orchestrator.

    Uses TrainingOrchestrator so the frontend can monitor progress via
    WebSocket and /training/status endpoint (instead of silent auto_retrain).
    """
    import asyncio

    from src.utils.constants import TRADABLE_ASSETS

    orch = getattr(request.app.state, "training_orchestrator", None)
    if orch is None:
        return success_response(
            {"message": "Training orchestrator non disponibile"}, status_code=503
        )

    if orch._running:
        return success_response({"message": "Training gia in corso"})

    async def _run():
        await orch.train_epics(list(TRADABLE_ASSETS))

    asyncio.create_task(_run(), name="manual_retrain_all")
    logger.info("Manual retrain-all triggered via orchestrator")

    return success_response({"message": "Retrain avviato per tutti gli asset attivi"})


@router.get("/training/status")
async def get_training_status(request: Request):
    """Get current training orchestrator status."""
    orch = getattr(request.app.state, "training_orchestrator", None)
    if orch is None:
        return error_response("Training orchestrator not initialized", 503)
    return success_response(orch.get_status())


@router.post("/training/start")
async def start_training(request: Request):
    """Start training for specified epics or all.

    Body (optional JSON):
        epics: list[str] — specific epics (default: all tradable)
        timeframe: str — "1h" (default)
        config: dict — optional training config overrides
    """
    import asyncio

    from src.utils.constants import TRADABLE_ASSETS

    orch = getattr(request.app.state, "training_orchestrator", None)
    if orch is None:
        return error_response("Training orchestrator not initialized", 503)
    if orch._running:
        return error_response("Training already in progress", 409)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    epics = body.get("epics") or list(TRADABLE_ASSETS)
    timeframe = body.get("timeframe", "1h")
    config = body.get("config", {})

    asyncio.create_task(orch.train_epics(epics, timeframe, config))

    return success_response(
        {
            "message": f"Training started for {len(epics)} epics",
            "epics": epics,
            "timeframe": timeframe,
        }
    )


@router.post("/training/start/{epic}")
async def start_training_single(request: Request, epic: str):
    """Start training for a single epic."""
    import asyncio

    orch = getattr(request.app.state, "training_orchestrator", None)
    if orch is None:
        return error_response("Training orchestrator not initialized", 503)
    if orch._running:
        return error_response("Training already in progress", 409)

    asyncio.create_task(orch.train_epics([epic]))

    return success_response(
        {
            "message": f"Training started for {epic}",
            "epic": epic,
        }
    )


# ──────────────────────────────────────────────────────────────────
# Extended data download endpoints
# ──────────────────────────────────────────────────────────────────


@router.post("/data/download-extended/{epic}")
async def download_extended_data(
    request: Request,
    epic: str = Path(...),
    days_back: int = Query(730, ge=1, le=3650),
):
    """Download extended historical data for an epic from free APIs.

    Runs in background and returns immediately.
    """
    from src.data.extended_data_provider import ExtendedDataProvider

    storage = getattr(request.app.state, "storage", None)

    provider = ExtendedDataProvider()

    async def _download():
        try:
            result = await provider.download_and_store(epic, days_back=days_back, storage=storage)
            logger.info("Extended download complete: {}", result)
        except Exception as exc:
            logger.error("Extended download failed for {}: {}", epic, exc)

    asyncio.create_task(_download(), name=f"download_extended_{epic}")

    return success_response(
        {
            "message": f"Download avviato per {epic} ({days_back} giorni)",
            "epic": epic,
            "days_back": days_back,
            "source": provider.get_best_source(epic),
        }
    )


@router.post("/data/download-extended")
async def download_extended_all(
    request: Request,
    days_back: int = Query(730, ge=1, le=3650),
):
    """Download extended data for all tradable assets (background)."""
    from src.data.extended_data_provider import ExtendedDataProvider
    from src.utils.constants import TRADABLE_ASSETS

    storage = getattr(request.app.state, "storage", None)

    provider = ExtendedDataProvider()
    epics = list(TRADABLE_ASSETS)

    async def _download_all():
        results = []
        for ep in epics:
            try:
                r = await provider.download_and_store(ep, days_back=days_back, storage=storage)
                results.append(r)
                logger.info("Extended download done: {}", r)
            except Exception as exc:
                logger.error("Extended download failed for {}: {}", ep, exc)
                results.append({"epic": ep, "bars_fetched": 0, "bars_new": 0, "error": str(exc)})
        logger.info("Extended download-all complete: {} epics processed", len(results))

    asyncio.create_task(_download_all(), name="download_extended_all")

    return success_response(
        {
            "message": f"Download avviato per {len(epics)} asset ({days_back} giorni)",
            "epics": epics,
            "days_back": days_back,
        }
    )
