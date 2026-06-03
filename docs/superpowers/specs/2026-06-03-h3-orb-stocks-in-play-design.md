# H3 ORB (stocks-in-play) — Design Spec (v1, 2026-06-03)

**Status:** DESIGN — approved in brainstorming. Terminal step = `writing-plans`.
**Parent:** Forward Demo Lab (`docs/strategy/FORWARD_LAB_SPEC.md`). H3 = Fase 2 (plug-in under the
existing `ForwardStrategy` ABC). H2 gap-fade is LIVE & autonomous; H1/H5 dead; H4 spike-fade later.

> Honest framing (inherited from the lab): post leak-fix MANTIS has no directional edge, so the
> baseline is EV-negative (random + spread + CFD financing). The forward demo is leak-immune and
> survivorship-immune by construction. H3 is a falsifiable forward hypothesis judged by the same
> statistical gauntlet (`factory_stats`) at N≥100 trades. Bold on the hypothesis, **uniform $200
> sizing** (no compounding/martingale) — concentration kills statistical power, not (fake) money.

## 1. Hypothesis

**H3 — Opening-Range Breakout on stocks-in-play.** On liquid US stock CFDs, the names with abnormal
early-session activity ("in play") that break their opening range continue in the break direction
through the session. Falsifiable: net-of-cost forward Sharpe/t-stat/DSR at N≥100; kill if bootstrap
CI ⊇ 0 or net ≤ 0 at real costs.

## 2. Approach (locked in brainstorming)

Faithful stocks-in-play ORB, built as a **vertical extension** of the existing lab:

- **RVOL screen** uses **real exchange volume via `yfinance`** (Yahoo). Capital.com's
  `lastTradedVolume` is a CFD platform tick/deal count (single/double digits) — NOT exchange share
  volume — so it cannot drive a faithful relative-volume screen. yfinance gives real per-minute
  share volume for free (already used across `scripts/ab/`).
- **Opening range + breakout detection + order execution** use **Capital.com** bars/prices (the
  execution venue) to avoid cross-venue skew on the breakout level.
- **Co-run with H2** on the single experiment account `'Account test'` (`322643372115580062`),
  multi-strategy, with **per-dealId P&L attribution** (closes a latent epic-match bug).

### Accepted data tradeoffs (yfinance, free — chosen over paid feed given the economic freeze)

| Constraint | Consequence | Mitigation |
|---|---|---|
| Yahoo intraday ~15min delayed | Can't reliably screen at open+15 | OR window = first **30min** (13:30–14:00 UTC); screen at open+30 |
| Yahoo 1-min history only ~7 days | 20-day baseline impossible from 1-min | Baseline from **5-min** bars (Yahoo serves ~60 days) |
| yfinance unofficial (rate-limit/break) | Screen may fail some days | Small pool (~30), retry, **skip-day graceful** (lab already skips on data failure) |

## 3. Components (isolated units)

| Unit | Responsibility | File | Depends on |
|---|---|---|---|
| `ORBStrategy(ForwardStrategy)` | `universe()`, `should_enter(ctx)` (breakout vs frozen OR, gated by RVOL eligibility), `exit_rule(pos,ctx)` (EOD flatten; SL is broker-side) | `scripts/ab/forward/strategy.py` | `ForwardStrategy`, `MarketContext` |
| `RvolScreener` | Compute per-epic RVOL from yfinance (today first-30min volume / trailing-20d baseline from 5-min bars); return eligible top-K. Network I/O isolated behind an injectable fetcher for tests | `scripts/ab/forward/screener.py` (new) | `yfinance` |
| `SessionState` | Per-day cache: `open_px[epic]`, `or_high[epic]`, `or_low[epic]`, `rvol[epic]`, `eligible: set[str]`. Built progressively by the scheduler; reset on date change | inside `scheduler.py` | — |
| `ExperimentScheduler` (extended) | Holds a **list** of strategies; `entry_pass` (every 5min, session window) builds ctx per (strategy, epic) from `SessionState` and calls `should_enter`; `mark_pass` dispatches `exit_rule` by `ledger.strategy`; `_realized` matches broker TRADE by **dealId** | `scripts/ab/forward/scheduler.py` | `ExperimentExecutor`, strategies |
| `forward_lab.py run` (extended) | Register strategy list `[GapFade, ORB]`; jobs: `entry_pass` 5min (13:30–16:00 window guard), `mark_pass` 15min, EOD flatten | `scripts/ab/forward_lab.py` | scheduler |

H2 `GapFadeStrategy`, `ForwardLedger`, `ExperimentExecutor`, `ForwardScorer` are **unchanged** except
where the cross-cutting fixes (§5) touch the scheduler.

## 4. Data flow (H3, one session)

```
13:30 UTC  entry_pass #1
            → SessionState.open_px[epic] = live mid (so H2 gap is stable across passes;
              identical to today's single-trigger behavior)
            → ORB ctx.or_high/or_low = None (OR not yet formed) → ORB.should_enter returns None
14:00 UTC  first entry_pass with OR formed:
            → SessionState._opening_range(epic): Capital.com MINUTE_5 bars 13:30–14:00
                 → or_high = max(high), or_low = min(low)
            → RvolScreener.select(pool, now): yfinance today first-30min vol / 20d baseline
                 → eligible = top-K names with RVOL ≥ threshold
14:00–16:00  entry_pass every 5min, for each eligible epic NOT already in ledger:
            → ctx = MarketContext(..., or_high, or_low, rvol, current_price=live mid)
            → ORB.should_enter:  price > or_high → BUY ; price < or_low → SELL ; else None
            → executor: MARKET $200 + hard SL broker-side (opposite OR side, ATR floor)
            → ledger.record_open(strategy="orb", ...); UNIQUE(strategy,epic,session_date) blocks re-entry
every 15min  mark_pass:
            → for each open row: strategy = registry[row["strategy"]]
            → exit_rule(pos, ctx):  ORB → now >= session_close (EOD) ;  H2 → 50%-fill | EOD
            → on exit (or broker-closed): close_position + realized P&L from broker TRADE matched by dealId
20:45 UTC  EOD flatten (mark_pass after session_close closes everything still open)
```

**Unification:** one `entry_pass` polls `should_enter` for ALL strategies every 5min. H2 fires on
pass #1 (gap known at open, open price cached); H3 fires whenever the breakout occurs. The ledger
UNIQUE constraint makes both idempotent under repeated polling. This same recurring-poll shape
hosts H4 (continuous spike-fade) in Fase 3.

## 5. Cross-cutting fixes (required for co-run)

1. **`MarketContext` extension** — add `or_high: float | None = None`, `or_low: float | None = None`,
   `rvol: float | None = None`. Frozen dataclass; H2 ignores them (defaults None).
2. **`_realized` by dealId** — match the broker TRADE transaction to the row's `deal_id`, not its
   epic. With H2 + H3 possibly holding opposite positions on the same epic the same day, epic-match
   misattributes P&L between strategies. CLAUDE.md confirms the TRADE row carries `dealId`
   (= `Position.deal_id`, deterministic key). **Verify `Transaction.deal_id` field exists at impl;**
   if a row's deal_id can't be matched (rotation), fall back to `PENDING_RECONCILE` (no invented P&L).
3. **`mark_pass` per-strategy dispatch** — look up the owning strategy via a `{name: strategy}`
   registry from `row["strategy"]` and call THAT strategy's `exit_rule`.
4. **Scheduler `strategy` → `strategies: list`** — construct with the full list; iterate in
   `entry_pass`. `forward_lab.py` builds `[GapFadeStrategy(...), ORBStrategy(...)]`.

## 6. H3 parameters (defaults, tunable via settings)

| Param | Default | Notes |
|---|---|---|
| Pool | ~30 liquid US large-cap CFDs (config list) | skip-graceful on missing epic / data |
| OR window | 13:30–14:00 UTC (30min) | dictated by Yahoo delay |
| Entry watch window | 14:00–16:00 UTC | breakout poll every 5min |
| RVOL baseline | trailing 20 trading days, first-30min volume, from 5-min bars (60d) | yfinance |
| RVOL eligibility | `RVOL ≥ 1.5`, take top-K = 5 | "stocks in play" |
| Breakout trigger | `price` beyond OR ± buffer (buffer default 0) | long+short |
| SL hard | opposite OR side, clamped to an ATR floor | broker-side, every trade |
| Sizing | $200 uniform | shared lab sizing; no compounding |
| Exit | broker SL + EOD flatten (no profit target) | H2 discipline + Zarattini EOD-exit |
| Concurrency | shared lab `max_concurrent` (default 5) + daily-loss-limit | scoped to experiment account |

Strategy `name = "orb"` → scorer reads `realized("orb")` independently of `"gap_fade"`.

**`entry_pass` window guard:** the 5-min interval job no-ops unless `now` is Mon–Fri within
13:30–16:00 UTC. H2 therefore fires on the first in-window pass (~13:30, capturing the open price)
exactly as its current single cron trigger does — the refactor preserves H2's open snapshot.

**Shared concurrency:** ORB top-K and H2 share the lab `max_concurrent` cap. If the cap is already
full (e.g. H2 positions open), surplus ORB breakouts simply don't fill that pass — expected
safety behavior, not an error. Both strategies draw from the same $200-uniform, daily-loss-limited
pool on the experiment account.

## 7. Isolation & invariants (unchanged from lab)

- Experiment runs on `'Account test'` via the dedicated `CAPITAL_EXPERIMENT_*` API key; the scalper
  stays OFF (it defaults to the same account → would collide). `assert_isolation()` re-checks the
  active account before every order.
- **P&L only from broker** (`Transaction.pl_value_in` / `Position.upl`) — never `(exit−entry)*size`.
- Hard SL broker-side on every trade. `datetime.now(timezone.utc).replace(tzinfo=None)` on any
  Postgres write (the lab ledger is SQLite, so N/A there).
- Technical math pure Polars/numpy (no ta-lib). pip + `.venv/Scripts/python.exe`.

## 8. Testing

- **Unit** (`backend/tests/forward/`):
  - `ORBStrategy.should_enter` table tests: break up → BUY, break down → SELL, inside range → None,
    `or_high`/`or_low` None → None, not-eligible → None, buffer respected.
  - `ORBStrategy.exit_rule`: EOD-only (now ≥ session_close → True, else False).
  - `RvolScreener`: synthetic volume series with injected fetcher → known RVOL + eligibility/top-K
    ranking; degraded/empty feed → empty eligible (skip-day).
  - `SessionState._opening_range`: synthetic MINUTE_5 bars → correct OR high/low; partial window.
  - `_realized` dealId-match: two TRADE txns same epic, different dealId → each row gets its own P&L;
    unmatchable dealId → `PENDING_RECONCILE`.
  - `mark_pass` multi-strategy dispatch: rows of mixed `strategy` → correct `exit_rule` applied.
- **Integration**:
  - `dry-run` extended: one `entry_pass` with OR formed logs intended ORB orders without sending.
  - yfinance live smoke (marked, network): `RvolScreener.select` over the pool returns numeric RVOL.
- **Scorer**: reuse `factory_stats` via `realized("orb")` (already per-strategy).
- **Regression**: run by subset (the full single-process Windows pytest run floods with pre-existing
  unrelated setup/teardown errors — known lab note).

## 9. Deploy

Implementing this **refactors the live H2 loop** (single 13:30 trigger → recurring `entry_pass`).
After merge: **restart** the detached run loop. H2 semantics are preserved (open price cached at the
first pass = today's existing 13:30 mid; ledger UNIQUE prevents re-entry). Sequence: stop old loop →
relaunch `forward_lab.py run` detached → confirm `run.err.log` shows both strategies registered.

## 10. Out of scope (YAGNI / later phases)

- H4 spike-fade (Fase 3 — continuous M1/M5 monitor + reinforced tail-risk guards).
- Profit targets / trailing for ORB (start SL+EOD only; revisit if forward stats warrant).
- Dynamic pool discovery via Capital.com market navigation (use a curated config list).
- Paid intraday data feed (frozen economics; yfinance free is sufficient for a demo).

## 11. File layout (delta)

```
scripts/ab/forward/strategy.py    # + MarketContext fields, + ORBStrategy
scripts/ab/forward/screener.py    # NEW — RvolScreener (yfinance, injectable fetcher)
scripts/ab/forward/scheduler.py   # SessionState, entry_pass, multi-strategy mark_pass, _realized by dealId
scripts/ab/forward_lab.py         # strategies list, entry_pass job, ORB universe/params wiring
backend/tests/forward/            # + test_orb_strategy.py, test_screener.py, test_session_state.py, test_realized_dealid.py
```

## 12. Confirm at implementation

- `Transaction.deal_id` field name/availability (for §5.2 dealId match).
- Capital.com epics for the ~30-name pool exist on demo (skip-graceful covers misses).
- yfinance symbol == Capital.com display epic for US large caps (trivial map; verify edge cases).
- Settings keys for ORB params (`forward_lab_orb_*`) added to config + `.env` defaults.
