# Agents/Strategy Audit — 2026-05-09

**Scope reviewed:** `agents/` (all), `drl/drl_ensemble_agent.py`, `strategy/strategy_router.py`, `models/prediction_service.py`, `llm_provider/`, `vision/vision_analyzer.py`, `tests/agents/`, `tests/conftest.py`.

---

## CRITICAL

### [orchestrator.py:139,157,174] MarketContext mutated in-place across agent pipeline

**Confidence: 95**

**What**: Vision step writes `context.vision_data = {...}` (139), `context.rag_context = ...` (157). DRL: `context.drl_signal = {...}` (174). `MarketContext` is Pydantic v2 mutable.

**Why it matters**: CLAUDE.md: "MarketContext is hub schema; agents must not mutate". If `paper_loop` reuses context across ticks, vision/DRL state leaks tick N → N+1.

**Fix**: `enriched = context.model_copy(update={...})`. Pass enriched downstream. Never mutate input.

---

## HIGH

### [debate.py:189] `min(key_resistance_levels)` wrong direction for BUY proximity check

**Confidence: 90**

**What**: BUY proximity: `nearest_resistance = min(technical.key_resistance_levels) < proposal.entry_price * 1.01`. For BUY, dangerous resistance is nearest *above* entry. `min()` picks globally lowest. Resistances `[1900.0, 2060.0]`, entry `2050` → `min=1900` (below entry) → check fires spurious BEAR.

**Why it matters**: Wrong BEAR pushes consensus bearish, FundManager rejects valid BUYs. Silent wrong-way bias live.

**Fix**: `min((r for r in key_resistance_levels if r > proposal.entry_price), default=None)`.

---

### [fund_manager.py:45 + orchestrator.py:226] "trader" appears twice in audit trail

**Confidence: 95**

**What**: `FundManagerAgent.decide()` appends `{"agent": "trader", ...}` to local trail (45). Orchestrator also appends "trader" (197). Merge at 226 → duplicate. Test `test_audit_trail_has_all_agents` uses set membership, doesn't catch.

**Fix**: Pick one owner. Remove other.

---

### [drl_ensemble_agent.py:59] Mutates returned Pydantic model `signal.action`

**Confidence: 85**

**What**: `signal.action = 0` mutates ensemble.predict() return. Bypasses schema validation. If predict() ever returns cached/shared singleton → corruption.

**Fix**: Construct new `DRLEnsembleSignal(action=0, ...)`.

---

### [llm_provider/factory.py:53] Unknown backend raises `ValueError`, not `LLMProviderError`

**Confidence: 85**

**What**: `ValueError` on misconfigured `LLM_BACKEND`. `MantisBaseAgent.analyze()` catches all (BLE001) → silent permanent HOLD all agents. Invisible to operator dashboards.

**Fix**: Raise `LLMProviderError` OR validate at startup.

---

## MEDIUM

### [vision_agent.py:107-118] Synthetic chart (seeded PRNG) sent to vision model

**Confidence: 80**

**What**: No OHLC → `np.random.seed(hash(epic) % 2**31)` + noise around `current_price`. Vision LLM analyzes fabricated data, returns BULL/BEAR derived from noise → flows into debate as real signal. Violates NO MOCK DATA spirit.

**Fix**: Return `_default_signal()` when no real OHLC.

---

### [base_agent.py:109-111] Fence stripping brittle

**Confidence: 82**

**What**: Only handles exact `\n` after `\`\`\``. Space-padded fence ` \`\`\` json ` passes `startswith` but fails strip. `vision_analyzer._strip_fences` more robust.

**Fix**: Share single fence-stripper utility.

---

### [orchestrator.py:90] `RISK_BLOCK_THRESHOLD` instance shadowing class variable

**Confidence: 80**

**What**: `orch.risk.RISK_BLOCK_THRESHOLD = X` creates instance attr shadowing class var. `RiskManagerAgent.RISK_BLOCK_THRESHOLD` still returns default `0.8`.

**Fix**: Move to `__init__` parameter.

---

### [schemas.py:158] `FinalDecision.agent_audit_trail` no `default_factory`

**Confidence: 80**

**What**: `**proposal.model_dump()` spread pattern (`fund_manager.py:92-98`) fragile. Adding required field without default → `ValidationError` runtime.

**Fix**: `Field(default_factory=list)`.

---

## LOW

- `technical_analyst.py:286-290` — confusing rationale ternary string concat
- `conftest.py:64-65` — `_disable_primaries_globally` doesn't cover `prediction_service.get_settings`

---

## Coverage Gaps

1. `VisionAgent._generate_chart()` synthetic-data fallback path — untested
2. Dual "trader" audit entry — set-membership test masks duplicate
3. Empty-debate + BUY proposal end-to-end — untested
4. **`backend/tests/strategies/` directory absent** — `strategy_router.py` ZERO test coverage
5. `DRLEnsembleAgent` empty ensemble path — untested
6. `LLMProvider.rerank()` not abstract — `FakeProvider` doesn't override → AttributeError if exercised

---

## Summary

**No `current_price`-as-SL/TP-trigger violation in agents layer.** `TraderAgent` uses `context.current_price` only to stamp `entry_price` on signal — sanctioned by CLAUDE.md. Actual SL/TP triggering remains in `paper_loop.py` (out of scope).

| Severity | Issue | Impact |
|----------|-------|--------|
| CRITICAL | MarketContext in-place mutation | Cross-tick context pollution if reused |
| HIGH | `min(resistance)` wrong direction in debate | Silent wrong-way BEAR bias on BUY |
| HIGH | "trader" duplicated audit trail | Misleading observability |
| HIGH | DRL `signal.action` mutation | Shared object corruption risk |
| HIGH | Unknown LLM_BACKEND ValueError | Silent permanent HOLD |
| MEDIUM | Synthetic chart to vision model | Vision signal from fabricated data |

`strategy_router.py` has ZERO test coverage. Conftest autouse fixture correctly handles agents suite.
