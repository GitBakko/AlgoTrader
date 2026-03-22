# MANTIS AI — Evolution Migration Notes

## Sprint 1: Multi-Agent Architecture

**Date:** 2026-03-22
**Branch:** `feature/evolution-multi-agent`

### What Changed

New package `backend/src/agents/` with 9 modules:
- `schemas.py` — Pydantic v2 contracts (AgentRole, MarketContext, TechnicalReport, SentimentReport, RiskReport, TradeProposal, DebateSummary, FinalDecision)
- `base_agent.py` — MantisBaseAgent ABC with Claude API integration
- `technical_analyst.py` — TechnicalAnalystAgent (LLM + heuristic fallback)
- `sentiment_analyst.py` — SentimentAnalystAgent (aggregates SIL feeds)
- `risk_manager_agent.py` — RiskManagerAgent (veto power at risk > 0.8)
- `trader_agent.py` — TraderAgent (combines reports into TradeProposal)
- `debate.py` — BullBearDebate (structured argumentation)
- `fund_manager.py` — FundManagerAgent (final approval/rejection)
- `orchestrator.py` — MantisAgentOrchestrator (coordinates full pipeline)

### Breaking Changes

**None.** The multi-agent system is entirely additive:
- Existing `generate_signal()` / `ScalpScoreStrategy` / `SignalGenerator` pipeline is **untouched**
- The orchestrator is gated by `AGENTS_ENABLED=false` (default OFF)
- When enabled, the orchestrator runs **alongside** the existing pipeline, enriching signal metadata
- No database schema changes
- No API contract changes

### New Dependencies

File: `backend/requirements_evolution.txt` (separate from main `requirements.txt`)
```
anthropic>=0.40.0  # Claude API for LLM-based agents
```

### New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTS_ENABLED` | `false` | Master toggle for multi-agent pipeline |
| `AGENTS_LLM_MODEL` | `claude-sonnet-4-20250514` | Claude model for agent reasoning |
| `AGENTS_TEMPERATURE` | `0.2` | LLM temperature |
| `AGENTS_MAX_TOKENS` | `2000` | Max tokens per LLM call |
| `AGENTS_TECHNICAL_WEIGHT` | `0.4` | Technical analysis weight |
| `AGENTS_SENTIMENT_WEIGHT` | `0.2` | Sentiment analysis weight |
| `AGENTS_RISK_WEIGHT` | `0.4` | Risk assessment weight |
| `AGENTS_RISK_BLOCK_THRESHOLD` | `0.8` | Risk score blocking threshold |
| `AGENTS_DEBATE_ENABLED` | `true` | Enable bull/bear debate step |
| `ANTHROPIC_API_KEY` | (empty) | Required when `AGENTS_ENABLED=true` |

### How to Activate

1. Install evolution deps: `pip install -r requirements_evolution.txt`
2. Set `ANTHROPIC_API_KEY` in `.env`
3. Set `AGENTS_ENABLED=true` in `.env`
4. Restart backend

### Architecture Notes

- `mantis/core/pipeline.py` from the evolution spec is replaced by direct wiring in `paper_loop.py` — avoids unnecessary abstraction
- `mantis/sil/` maps to existing `backend/src/external/` + `backend/src/features/sil_features.py`
- FundamentalsAnalyst intentionally excluded: MANTIS trades crypto/forex where traditional fundamentals are less applicable; macro data is covered by RAG pipeline (Sprint 4)
- Every LLM-based agent has a `_heuristic_analyze()` fallback that works without any API calls

### Test Coverage

290+ agent-specific tests across 8 test files in `backend/tests/agents/`.
All existing tests (~1487) continue to pass with zero regressions.
