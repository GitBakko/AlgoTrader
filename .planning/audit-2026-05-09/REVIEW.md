# MANTIS Codebase Audit — Consolidated Review — 2026-05-09

4 parallel reviewers. Findings ranked by production impact.

## CRITICAL (block LIVE deploy)

| # | File:Line | Issue | Source |
|---|-----------|-------|--------|
| **C1** | `state_recovery.py:218,298` | `_load_positions_from_broker` returns `list[Position]` typed as `list[dict]`. `_reconcile_positions` crashes silent on every DEMO/LIVE restart with open positions. Documented in `project_state_recovery_position_bug.md`, **NOT FIXED**. Combined with M1 (key mismatch), SL/TP enforcement absent for restarted positions. | 02-trading-loop |
| **C2** | `paper_loop.py:1121` | `_broker_closed_deals = set()` reset every `_detect_broker_closed` call. Cross-tick race: `_finalize_close` suspended at await → next tick voids guard → redundant `close_position` broker call → can re-open position. | 02-trading-loop |
| **C3** | `orchestrator.py:139,157,174` | `MarketContext` mutated in-place by vision/DRL steps. If `paper_loop` reuses context across ticks, vision/DRL state leaks. | 04-agents-strategy |

## HIGH (production-impacting)

| # | File:Line | Issue | Source |
|---|-----------|-------|--------|
| H1 | `state_recovery.py:694` + `main.py` | `rehydrate_pending_closes` never wired at startup. Tier 2 retry queue resets every restart. | 02 |
| H2 | `paper_loop.py:1174,1416` | v2 `CloseDetector.detect()` called twice per tick → 4× extra broker calls → 429 throttle risk. | 02 |
| H3 | `paper_loop.py:1006` | Transaction cache TTL 60s vs reconciler 15s → misses settled closes ticks 2-4. | 02 |
| H4 | `paper_loop.py:3640` | Time-stop `continue` always fires even on `result.success=False` → SL/TP skipped on failed close (weekend index gap-open risk). | 02 |
| H5 | `debate.py:189` | `min(key_resistance_levels)` picks globally lowest. For BUY proximity check, dangerous resistance is *nearest above entry*. Spurious BEAR fires when resistance below entry exists → silent wrong-way bias. | 04 |
| H6 | `fund_manager.py:45` + `orchestrator.py:226` | "trader" appears twice in every `agent_audit_trail`. Test masked by set-membership check. | 04 |
| H7 | `drl_ensemble_agent.py:59` | `signal.action = 0` mutates Pydantic model returned by `predict()`. Bypasses validation. | 04 |
| H8 | `llm_provider/factory.py:53` | Unknown `LLM_BACKEND` raises `ValueError`, NOT `LLMProviderError`. `MantisBaseAgent.analyze()` BLE001-catches → silent permanent HOLD all agents on misconfigured env. | 04 |
| H9 | `ollama_provider.py:54-67,235-241` | Reranker first-load race: 15 concurrent epics can both pass None-check → double 568 MB HF download. No asyncio.Lock. | 03 |
| H10 | `ollama_provider.py:91` | `asyncio.get_event_loop()` instead of `get_running_loop()`. Python 3.14 `RuntimeError`. | 03 |
| H11 | `index_mantis_docs.py:169-175` | All chunks/file in single embed call → CLAUDE.md/STYLE_BIBLE.md may exceed 60s timeout → silently skipped → corpus missing critical knowledge. | 03 |
| H12 | `vector_store.py:22` + `context_builder.py:402` | `MantisVectorStore` default dim 384 vs bge-m3 1024. MiniLM fallback raises `ValueError` on `add()`. | 03 |
| H13 | `tests/risk/test_risk_manager.py:24` + `risk_manager.py:340` | `_non_scalp_settings` mock unset `min_signal_rr_threshold`. `MagicMock.__float__()=1.0` → all autouse tests run §4-ter at threshold 1.0 vs prod 0.40. R:R floor coverage essentially zero. | 01 |

## MEDIUM (correctness concerns)

| # | File:Line | Issue | Source |
|---|-----------|-------|--------|
| M1 | `state_recovery.py:259` | DB-recovered positions use `stop_loss`/`take_profit` keys; `paper_loop.py:3587` reads `stop_level`/`profit_level`. SL enforcement absent post-restart. **Compounds C1.** | 02 |
| M2 | `api/routers/trading.py:674` | Emergency stop alert WARNING, gated on `alerts_enabled`. Invariant #4 says CRITICAL unconditional. | 02 |
| M3 | `state_recovery.py:314` | `_reconcile_positions` auto-closes DB-only positions reason "EXTERNAL", no P&L, no UNRECONCILED alert. | 02 |
| M4 | `paper_loop.py:459` | `trailing_stop_manager._positions` mutation pop+set non-atomic. Architectural fragility. | 02 |
| M5 | `vision_agent.py:107-118` | Synthetic seeded-PRNG chart sent to vision LLM when no OHLC → debate signal from fabricated data. | 04 |
| M6 | `base_agent.py:109-111` | Fence-stripping brittle on space-padded fences. | 04 |
| M7 | `orchestrator.py:90` | `RISK_BLOCK_THRESHOLD` instance shadowing class var. | 04 |
| M8 | `schemas.py:158` | `FinalDecision.agent_audit_trail` no `default_factory`. `**model_dump()` spread fragile. | 04 |
| M9 | `index_mantis_docs.py:108` | Markdown headers inside ` ``` ` fences split chunks mid-block. | 03 |
| M10 | `context_builder.py:389` | `_load_corpus` re-stat per call when corpus empty. | 03 |
| M11 | `api/routers/agents.py:44` | `/status` reports stale `claude-sonnet-4-20250514` after Phase 14b migration. | 03 |
| M12 | `base_agent.py:109` | `_call_llm` `rsplit("\`\`\`", 1)[0]` truncates JSON with embedded triple-backticks. | 03 |
| M13 | `trailing_stop_manager.py:304` | `_derive_tp_levels` guard direction-unaware. Wrong-side SELL TP → immediate breakeven. | 01 |
| M14 | `correlation_guard.py:124` | No floor on `size_multiplier`; numpy drift `abs_corr > 1.0` → negative size. | 01 |
| M15 | `trailing_stop_manager.py:385` | `lowest_price or entry_price` falsy-zero substitution. | 01 |

## LOW (code quality)

7 items across 4 reports. See individual files.

## Coverage Gaps (by impact)

1. **`backend/tests/strategies/` directory ABSENT** — `strategy_router.py` zero test coverage despite recent MR/ML primary chain changes (04)
2. R:R floor §4-ter — zero dedicated tests at production threshold 0.40 (01)
3. USDCHF/USDCAD pip-aware sizing — only USDJPY covered (01)
4. C1 (Position-vs-dict) crash path — never exercised in tests
5. `OllamaProvider.rerank()` — zero tests (03)
6. `_LocalCrossEncoder` real transformers path — untested
7. Dual "trader" audit entry — masked by set-membership (04)
8. Empty-DRL-ensemble path (04)
9. Time-stop close-failure path (H4)
10. `_broker_closed_deals` cross-tick voiding (C2)

---

## Recommended Fix Order

**Tier 1 (block LIVE deploy):** C1, C2, M1 (compound). C3 (orchestrator mutation).

**Tier 2 (before next agent improvement push):** H5 (debate direction), H8 (factory ValueError), H1 (rehydrate startup), H9 (rerank lock).

**Tier 3 (sweep with test improvements):** H2/H3 (cache+double-fetch), H4 (time-stop), H13 (R:R test fidelity), H11 (embed batching), M11 (status string).

**Tier 4 (cleanup):** all M and L items + coverage gaps.

---

## Files

- [01-risk-sizing.md](01-risk-sizing.md)
- [02-trading-loop.md](02-trading-loop.md)
- [03-llm-rag.md](03-llm-rag.md)
- [04-agents-strategy.md](04-agents-strategy.md)
