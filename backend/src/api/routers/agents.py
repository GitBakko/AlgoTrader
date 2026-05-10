# MANTIS-EVOLUTION: Multi-Agent Pipeline API Router
"""
Multi-Agent Pipeline API endpoints.

Endpoints:
  GET  /api/agents/status              — Agent system status (enabled, modules, config)
  POST /api/agents/analyze/{epic}      — Trigger manual agent analysis for an epic
  GET  /api/agents/last-decision/{epic} — Last agent decision from the paper loop
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from loguru import logger

from src.agents.schemas import MarketContext
from src.utils.config import get_settings

router = APIRouter()


def _success(data):
    return {"success": True, "data": data}


def _error(msg: str, status: int = 400):
    """H1-API fix: return JSONResponse with the requested status code so
    the prior plain-dict return (HTTP 200 regardless of `status`) stops
    masking 403/503 as success."""
    from fastapi.responses import JSONResponse  # noqa: PLC0415
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": msg},
    )


@router.get("/status")
async def agents_status():
    """Get multi-agent pipeline status and configuration."""
    settings = get_settings()
    # M11 fix: report the active LLM provider + model. Previously this
    # always returned the stale "claude-sonnet-4-20250514" default of
    # `agents_llm_model` even after Phase 14b migrated the agent layer
    # to the LLMProvider abstraction (Ollama / qwen3.6:35b).
    llm_label = "unknown"
    try:
        from src.llm_provider.factory import get_llm_provider  # noqa: PLC0415

        provider = get_llm_provider()
        provider_name = type(provider).__name__
        gen_model = getattr(provider, "generation_model", None)
        llm_label = f"{provider_name}/{gen_model}" if gen_model else provider_name
    except Exception:
        pass
    return _success(
        {
            "agents_enabled": settings.agents_enabled,
            "vision_enabled": settings.vision_enabled,
            "drl_enabled": settings.drl_enabled,
            "debate_enabled": settings.agents_debate_enabled,
            "orchestrator_active": settings.agents_enabled,
            "llm_model": llm_label,
        }
    )


@router.post("/analyze/{epic}")
async def analyze_epic(epic: str, request: Request):
    """
    Trigger a manual multi-agent analysis for the given epic.
    Requires AGENTS_ENABLED=true.

    Runs the full orchestrator pipeline in heuristic mode (no LLM calls).
    Returns the FinalDecision produced by the FundManagerAgent.
    """
    settings = get_settings()
    if not settings.agents_enabled:
        return _error("Multi-agent pipeline is disabled. Set AGENTS_ENABLED=true to enable.", 403)

    try:
        from src.agents.orchestrator import MantisAgentOrchestrator

        orchestrator = MantisAgentOrchestrator(
            debate_enabled=settings.agents_debate_enabled,
            vision_enabled=False,  # skip LLM-backed vision for manual trigger
            drl_enabled=False,  # skip DRL for manual trigger
        )

        # Build a minimal context — price unknown without live feed
        loop = getattr(request.app.state, "paper_loop", None)
        current_price = 0.0
        equity = 0.0
        open_positions = 0

        if loop is not None:
            try:
                last_signals = getattr(loop, "_last_signals", {})
                sig = last_signals.get(epic, {})
                if sig.get("current_price"):
                    current_price = float(sig["current_price"])
            except Exception:
                pass

            try:
                account = getattr(loop, "_account_info", None)
                if account and hasattr(account, "get"):
                    equity = float(account.get("equity", 0.0))
            except Exception:
                pass

            try:
                positions = getattr(loop, "_positions", {})
                open_positions = len(positions) if positions else 0
            except Exception:
                pass

        context = MarketContext(
            epic=epic,
            current_price=current_price,
            atr=1.0,
            equity=equity,
            open_positions=open_positions,
        )

        decision = await orchestrator.run(context)

        return _success(
            {
                "epic": epic,
                "action": decision.action,
                "approved": decision.approved,
                "confidence": decision.confidence,
                "size_pct": decision.size_pct,
                "entry_price": decision.entry_price,
                "stop_loss": decision.stop_loss,
                "take_profit_levels": decision.take_profit_levels,
                "rationale": decision.rationale,
                "override_reason": decision.override_reason,
                "debate_summary": decision.debate_summary,
                "agent_audit_trail": decision.agent_audit_trail,
            }
        )

    except Exception as e:
        logger.error(f"Agent analysis failed for {epic}: {e!r}")
        return _error(f"Agent analysis failed: {e}")


@router.get("/last-decision/{epic}")
async def last_decision(epic: str, request: Request):
    """
    Get the last agent decision recorded by the paper loop for the given epic.

    Returns the agent_decision dict stored in the loop's _last_signals, or null
    if no agent decision has been recorded yet (AGENTS_ENABLED=false or loop not
    yet processed this epic).
    """
    loop = getattr(request.app.state, "paper_loop", None)

    if loop is None:
        return _success({"epic": epic, "agent_decision": None, "reason": "loop_not_running"})

    try:
        last_signals: dict = getattr(loop, "_last_signals", {})
        signal_info = last_signals.get(epic)

        if signal_info is None:
            return _success({"epic": epic, "agent_decision": None, "reason": "no_signal_yet"})

        agent_decision = signal_info.get("agent_decision")
        return _success(
            {
                "epic": epic,
                "agent_decision": agent_decision,
                "signal_timestamp": signal_info.get("timestamp"),
            }
        )

    except Exception as e:
        logger.error(f"Failed to retrieve last agent decision for {epic}: {e!r}")
        return _error(f"Failed to retrieve last decision: {e}")
