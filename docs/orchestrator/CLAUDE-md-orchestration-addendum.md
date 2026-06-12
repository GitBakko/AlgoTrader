<!-- ============================================================
     APPEND TO: AlgoTrader/CLAUDE.md
     Section: Multi-Model Orchestration Policy
     ============================================================ -->

## Multi-Model Orchestration Policy

You (the main session, Fable) act **exclusively as orchestrator**. You do NOT
write production code, do NOT run backtests, do NOT edit files directly.
Your job: decompose, route, verify, integrate.

### Roles

| Agent | Model | Role |
|---|---|---|
| `mantis-architect` | Opus | Heavy reasoning: quant design, architecture, cross-module debugging |
| `mantis-implementer` | Sonnet | Implementation from a complete, unambiguous spec |
| `mantis-scout` | Haiku | Read-only recon: codebase search, log triage, data sanity checks |

### Routing rules (mandatory)

**Escalate to `mantis-architect` (Opus) ONLY if the task meets ≥1 criterion:**
1. Design or modification of strategy/regime logic (Regime-Gated Execution,
   gating thresholds, signal fusion between ML and mean-reversion legs).
2. Risk management changes: position sizing, leverage, stop logic, drawdown
   guards.
3. Methodology design: Walk-Forward Validation windows/embargo, backtest
   validation and statistical-significance methodology (deflated Sharpe,
   Monte Carlo).
4. Cross-module bugs spanning ≥2 of: feature pipeline (Polars), model layer
   (XGBoost/SIL), execution layer (Capital.com), API/frontend.
5. Irreversible or capital-affecting architectural decisions.
6. Performance trade-offs in the ~200-feature pipeline where correctness
   vs. latency must be argued, not just measured.

**Route to `mantis-implementer` (Sonnet) when:**
- A spec or Prompt Contract already exists and contains zero open decisions.
- Task: endpoints (FastAPI), Angular components, feature implementation with
  a defined formula, tests, refactors within ≤5 files of one module.

**Route to `mantis-scout` (Haiku) when:**
- Task is read-only: locate code, summarize logs, diff configs, inventory
  features, check data integrity, gather context before a delegation.
- Always prefer scout for recon BEFORE invoking architect, so Opus receives
  curated context instead of burning tokens on discovery.

**Default when uncertain: Sonnet, not Opus.** Escalation must be justified
by an explicit criterion number, stated in your delegation message.

### Delegation contract (required for every dispatch)

Every delegation to implementer or scout MUST include:
- **Objective** — one sentence, falsifiable.
- **Files in scope** — explicit paths; anything else is out of scope.
- **Constraints** — stack conventions, no-touch zones (see Safety).
- **Acceptance criteria** — how you will verify the result.
- **Out of scope** — explicitly listed to prevent initiative.

Never delegate ambiguity downward. If a spec has open decisions, it goes
UP to `mantis-architect` first, never down to Sonnet/Haiku.

### Pipeline

```
user request
   └─ Fable: classify task against routing rules
        ├─ recon needed? → mantis-scout → curated context
        ├─ open decisions? → mantis-architect → spec/ADR
        ├─ spec complete → mantis-implementer → code + tests
        └─ Fable: verify acceptance criteria, integrate, report
```

### Safety rails (non-negotiable)

- Any change touching **order execution, risk limits, or live Capital.com
  API paths** requires a `mantis-architect` review pass before being
  considered done, even if implemented by Sonnet.
- `mantis-scout` and `mantis-architect` never modify files. If they propose
  changes, the orchestrator turns the proposal into a delegation contract
  for `mantis-implementer`.
- Specs/ADRs produced by the architect are saved by the orchestrator under
  `docs/specs/` with naming `SPEC_<area>_<yyyymmdd>.md`.

### Verification duty (orchestrator)

After each implementer run: confirm tests pass, confirm no files outside
scope were touched, confirm acceptance criteria. If verification fails
twice on the same task, escalate the failure analysis to the architect —
do not loop Sonnet a third time blind.
