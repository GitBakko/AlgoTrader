"""
Strategy API router.
Manages strategy configuration, portfolio allocation, and risk limits.
"""

from fastapi import APIRouter, Depends

from src.api.dependencies import get_risk_manager, get_strategy_manager
from src.api.schemas import (
    AllocationResponse,
    RiskLimitsResponse,
    StrategyConfigResponse,
    error_response,
    success_response,
)
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.schemas import StrategyConfig
from src.strategy.strategy_manager import StrategyManager
from src.utils.constants import ALL_ASSETS

router = APIRouter()

SUPPORTED_EPICS = ALL_ASSETS


@router.get("/config")
async def get_strategy_config(
    manager: StrategyManager = Depends(get_strategy_manager),
):
    """Get strategy configuration for all supported assets."""
    configs = []
    for epic in SUPPORTED_EPICS:
        cfg = manager._get_config(epic)
        configs.append(
            StrategyConfigResponse(
                epic=cfg.epic,
                min_confidence=cfg.min_confidence,
                counter_trend_penalty=cfg.counter_trend_penalty,
                stop_multiplier=cfg.stop_multiplier,
                risk_reward_ratio=cfg.risk_reward_ratio,
                overbought_rsi=cfg.overbought_rsi,
                oversold_rsi=cfg.oversold_rsi,
            ).model_dump()
        )

    return success_response(configs)


@router.put("/config")
async def update_strategy_config(
    config: StrategyConfigResponse,
    manager: StrategyManager = Depends(get_strategy_manager),
):
    """Update strategy configuration for an asset."""
    if config.epic not in SUPPORTED_EPICS:
        return error_response(f"Unsupported epic: {config.epic}")

    new_config = StrategyConfig(
        epic=config.epic,
        min_confidence=config.min_confidence,
        counter_trend_penalty=config.counter_trend_penalty,
        stop_multiplier=config.stop_multiplier,
        risk_reward_ratio=config.risk_reward_ratio,
        overbought_rsi=config.overbought_rsi,
        oversold_rsi=config.oversold_rsi,
    )
    manager._configs[config.epic] = new_config

    return success_response({"epic": config.epic, "updated": True})


@router.get("/allocation")
async def get_allocation(
    regime: str | None = None,
    manager: StrategyManager = Depends(get_strategy_manager),
):
    """Get current portfolio allocation weights."""
    weights = manager.get_allocation(regime)

    return success_response(AllocationResponse(weights=weights, regime=regime).model_dump())


@router.get("/risk-limits")
async def get_risk_limits(
    risk_mgr: RiskManager = Depends(get_risk_manager),
):
    """Get current risk limits."""
    limits = risk_mgr.limits

    return success_response(
        RiskLimitsResponse(
            max_risk_per_trade=limits.max_risk_per_trade,
            max_daily_drawdown=limits.max_daily_drawdown,
            max_total_drawdown=limits.max_total_drawdown,
            max_position_pct=limits.max_position_pct,
        ).model_dump()
    )


@router.put("/risk-limits")
async def update_risk_limits(
    body: RiskLimitsResponse,
    risk_mgr: RiskManager = Depends(get_risk_manager),
):
    """Update risk limits."""
    # Preserve existing max_total_open_positions / max_total_exposure on PUT
    # (these are wired from env Settings, not exposed in the body schema).
    risk_mgr.limits = RiskLimits(
        max_risk_per_trade=body.max_risk_per_trade,
        max_daily_drawdown=body.max_daily_drawdown,
        max_total_drawdown=body.max_total_drawdown,
        max_position_pct=body.max_position_pct,
        max_total_open_positions=risk_mgr.limits.max_total_open_positions,
        max_total_exposure=risk_mgr.limits.max_total_exposure,
    )

    return success_response({"updated": True})
