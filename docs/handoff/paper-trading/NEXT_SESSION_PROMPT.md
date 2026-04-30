# Paper Trading v2 — Next Session Prompt (2026-04-27 → ...)

Drop this file's content as the **first user message** of the next session.
Memory + claude-mem are already updated; this is the conversational on-ramp.

---

## Context recap

Paper Trading v2 cockpit revamp is **4 PRs deep** and stacked on `main`:

| PR | Branch | Base | Scope |
|---|---|---|---|
| [#8](https://github.com/GitBakko/AlgoTrader/pull/8)  | `ui/paper-trading-v2-shell`        | `main`  | HDR-01 cockpit-header + 3-col layout + TS contracts |
| [#9](https://github.com/GitBakko/AlgoTrader/pull/9)  | `ui/paper-trading-v2-left-rail`    | `#8`   | bot-vitals + risk-gauges + models-health |
| [#10](https://github.com/GitBakko/AlgoTrader/pull/10) | `ui/paper-trading-v2-center-hero`  | `#9`   | KPI strip + position-card + active-positions-cockpit |
| [#11](https://github.com/GitBakko/AlgoTrader/pull/11) | `ui/paper-trading-v2-real-history` | `#10`  | 60s P&L snapshot system + resilient logos + USDJPY analysis |

The stack is mergeable bottom-up. After PR #8 lands on `main` GitHub auto-rebases #9, #10 follows, etc.

Local working backend was restarted twice this session — last restart picked up the live mid-price fix on commit `1dd1a2f`.

## Hard invariants surfaced this session

- **NO MOCK DATA NELLE MASCHERE.** Charts/sparklines/lists must source from persisted backend tables. No synthetic ramps, no in-memory ws-only ring buffers, no fabricated placeholders. KPI sparklines read `paperPnlHistory()`; position-card chart reads `positionPnlHistory()[deal_id]`.
- **`Position` broker model has NO `current_price` field** — only `level` (entry) and `upl`. Live mid-price comes from the WS quote stream, REST `get_market_details(epic).snapshot.{bid,offer}`, or UPL reconstruction.
- Token rules unchanged: `var(--mantis-*)` only, mono with `tnum` for any number, radius 4/6/100, no 8/12/16/20.

## What's left

### A · PR5 — drawer + skeleton + audit

Last item in `docs/handoff/paper-trading/HANDOFF.md` §10. Three components on a new branch `ui/paper-trading-v2-drawer`, base = `ui/paper-trading-v2-real-history`:

1. **`position-detail-drawer`** (HANDOFF §3.9, MDL-02). Right-side 380px slide-in. Header sticky with title + close + tab strip (`Overview · Audit · History`). Body placeholder for now — wire `SignalAuditService.openByDealId(deal_id)` for the Audit tab so existing audit drawer logic is reused. Surface from `position-card.detailsClicked` output.
2. **Skeleton loading** — replace empty/initial states with shimmer cards on:
   - `active-positions-cockpit` first paint before `paperPositions()` resolves
   - `live-feed-timeline` (currently still a placeholder, may be merged with PR4 leftovers)
   - `kpi-strip-compact` per-cell shimmer when `paperPnlHistory()` is null
   Use `frontend/src/app/shared/components/skeleton-card` / `skeleton-table` if compatible, else add a new `skeleton-kpi`.
3. **Style Bible §3 audit pass** — run the VIO-01..12 checklist against the new page and fix any violations. Document the diff in the PR body.

DoD checklist already in HANDOFF §9.

### B · USDJPY micro-position fix

Open PR off `main` (separate from the cockpit stack):

- Branch: `fix/min-position-floor`.
- Add settings:
  - `MIN_TP_PCT` (default `0.0015` = 0.15%), override `MIN_TP_PCT_FOREX` via asset-class lookup.
  - `MIN_RISK_AMOUNT_USD` (default `5.0`).
- Strategy layer: enforce `tp_distance >= entry * MIN_TP_PCT` (signed by direction) in:
  - `backend/src/strategy/scalp_score_strategy.py::ScalpScoreStrategy.calculate_levels`
  - `backend/src/strategy/mean_reversion_strategy.py::MeanReversionStrategy.calculate_tp`
- Sizer/risk layer: in `RiskManager.evaluate_signal`, after sizing compute `risk_amount = position_size * stop_distance` and reject with `error.min_notional` if `< MIN_RISK_AMOUNT_USD`. Surface in the rejected-signals feed (don't auto-scale up).
- Tests: update `tests/risk/test_risk_manager.py` and `tests/strategy/*` to expect the new floors. Targeted backtest sweep on the 21-asset universe before merge.
- Reference doc: `docs/reports/2026-04-27_usdjpy_micro_position_analysis.md`.

### C · Verification list (run when returning)

```bash
# 1. Backend running on the latest stack head?
curl -s http://localhost:8000/api/trading/pnl-history?minutes=10 | jq '.data.points | length'
# Expected: > 0 after a few minutes of uptime

# 2. Snapshot rows have varying current_price?
cd backend && .venv/Scripts/python.exe -c "
import asyncio
from src.database.session import DatabaseManager
async def main():
    DatabaseManager.initialize()
    async with DatabaseManager.session() as s:
        from sqlalchemy import text
        r = await s.execute(text(
            \"SELECT epic, COUNT(DISTINCT current_price) FROM position_pnl_snapshots \"
            \"WHERE captured_at > NOW() - INTERVAL '5 minutes' GROUP BY epic\"
        ))
        for row in r:
            print(row)
asyncio.run(main())
"
# Expected: each open epic has > 1 distinct price

# 3. Frontend build clean
cd frontend && npx ng build --configuration=development 2>&1 | tail -10
```

### D · Optional follow-ups

- Re-run **graphify** (`/graphify`) once PR #11 lands on `main` — backend graph will pick up the new `pnl_snapshot_scheduler` module + repository + endpoints. Last build was on commit `77746a2f` (pre-session).
- Frontend **dispatching-parallel-agents** opportunity: PR5 drawer / skeleton / audit are independent and can be parallelised.
- Consider adding a Prometheus counter for `paper_pnl_snapshot_total{kind="paper|position"}` so ops can see the 60s tick alive without DB peeking.

## Useful starting commands

```bash
cd /d/Develop/AI/_ClaudeCode/AlgoTrader

# Pick up the stack
git fetch origin
git checkout ui/paper-trading-v2-real-history
git status

# If starting PR5
git checkout -b ui/paper-trading-v2-drawer

# If starting USDJPY fix
git checkout main && git pull
git checkout -b fix/min-position-floor

# Dev
cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
cd frontend && npx ng serve --port 4321
```

## Memory cross-references

- `project_paper_trading_v2_2026-04-27.md` — branch + commit map
- `project_pnl_snapshot_system_2026-04-27.md` — backend snapshot architecture
- `project_logo_service_resilient_2026-04-27.md` — logo URL chain pattern
- `project_usdjpy_micro_position_2026-04-27.md` — sizing fix root cause
- claude-mem observations #19530 / #19533 / #19534

---

*Generated 2026-04-27 from CAVEMAN-mode session.*
