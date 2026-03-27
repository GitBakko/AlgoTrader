# MANTIS-EVOLUTION: DRL Ensemble API Router
"""
DRL Ensemble API endpoints.

Endpoints:
  GET  /api/drl/status    — DRL config and enabled state
  GET  /api/drl/ensemble  — Ensemble status (agents, voting mode)
  POST /api/drl/predict   — Manual prediction for an epic (if enabled)
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from loguru import logger

from src.utils.config import get_settings

router = APIRouter()


def _success(data):
    return {"success": True, "data": data}


def _error(msg: str, status: int = 400):
    return {"success": False, "error": msg}


@router.get("/status")
async def drl_status():
    """Get DRL Ensemble configuration and enabled state."""
    settings = get_settings()
    return _success(
        {
            "drl_enabled": settings.drl_enabled,
            "algorithms": settings.drl_algorithms,
            "voting_mode": settings.drl_voting_mode,
            "confidence_threshold": settings.drl_confidence_threshold,
            "ensemble_weight": settings.drl_ensemble_weight,
            "total_timesteps": settings.drl_total_timesteps,
            "retrain_interval_days": settings.drl_retrain_interval_days,
            "train_test_split": settings.drl_train_test_split,
            "min_sharpe_for_deploy": settings.drl_min_sharpe_for_deploy,
            "max_drawdown_for_deploy": settings.drl_max_drawdown_for_deploy,
        }
    )


@router.get("/ensemble")
async def drl_ensemble_info(request: Request):
    """
    Get current DRL ensemble status.

    Returns agent names, voting mode, and whether the ensemble is active.
    The ensemble lives on app.state.drl_ensemble when DRL is enabled.
    """
    settings = get_settings()
    if not settings.drl_enabled:
        return _success(
            {
                "active": False,
                "reason": "DRL_ENABLED=false",
                "agent_count": 0,
                "agents": [],
                "voting_mode": settings.drl_voting_mode,
            }
        )

    ensemble = getattr(request.app.state, "drl_ensemble", None)
    if ensemble is None:
        return _success(
            {
                "active": False,
                "reason": "Ensemble not initialised yet",
                "agent_count": 0,
                "agents": [],
                "voting_mode": settings.drl_voting_mode,
            }
        )

    agent_info = []
    for name, agent in ensemble.agents.items():
        agent_info.append(
            {
                "name": name,
                "algorithm": getattr(agent, "algorithm_name", name),
                "is_trained": getattr(agent, "is_trained", False),
                "best_regime": getattr(agent, "best_regime", []),
            }
        )

    return _success(
        {
            "active": True,
            "agent_count": ensemble.agent_count,
            "agents": agent_info,
            "voting_mode": ensemble.voting_mode,
            "confidence_threshold": ensemble.confidence_threshold,
        }
    )


@router.post("/predict")
async def drl_predict(
    request: Request,
    epic: str = Query(..., description="Asset epic (e.g., XAUUSD)"),
    regime: str = Query(default="UNKNOWN", description="Current market regime"),
):
    """
    Run a manual DRL ensemble prediction for the given asset.

    Requires DRL_ENABLED=true and a live ensemble on app.state.drl_ensemble.
    The observation is built from synthetic/demo data when no live price feed
    is available.
    """
    settings = get_settings()
    if not settings.drl_enabled:
        return _error("DRL Ensemble is disabled. Set DRL_ENABLED=true to enable.", 403)

    ensemble = getattr(request.app.state, "drl_ensemble", None)
    if ensemble is None:
        return _error("DRL Ensemble is not initialised.", 503)

    try:
        import numpy as np

        # Build a minimal observation vector.
        # In production this would be filled from the live feature pipeline.
        obs = np.zeros(6, dtype=np.float32)

        # Try to pull a real observation from the trading loop if available
        loop = getattr(request.app.state, "paper_loop", None)
        if loop is not None:
            try:
                data_store = getattr(loop, "data_store", None) or getattr(loop, "_data_store", None)
                if data_store is not None:
                    import polars as pl

                    df = await data_store.get_latest(epic, bars=12)
                    if df is not None and len(df) >= 2 and "close" in df.columns:
                        closes = df["close"].to_numpy()
                        rets = np.diff(closes) / closes[:-1]
                        obs[0] = float(rets[-1]) if len(rets) > 0 else 0.0
                        obs[1] = float(np.mean(rets))
                        obs[2] = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
                        obs[3] = float(closes[-1] / closes[0] - 1) if closes[0] != 0 else 0.0
            except Exception as exc:
                logger.debug(f"[DRL predict] Could not build obs from data store: {exc!r}")

        signal = ensemble.predict(obs, current_regime=regime)

        action_labels = {0: "HOLD", 1: "BUY", 2: "SELL"}
        return _success(
            {
                "epic": epic,
                "regime": regime,
                "action": signal.action,
                "action_label": action_labels.get(signal.action, "HOLD"),
                "confidence": signal.confidence,
                "contributing_agents": signal.contributing_agents,
                "voting_mode": signal.voting_mode,
                "regime_match": signal.regime_match,
                "agent_votes": signal.agent_votes,
            }
        )

    except Exception as exc:
        logger.error(f"[DRL predict] Failed for {epic}: {exc!r}")
        return _error(f"DRL prediction failed: {exc}")
