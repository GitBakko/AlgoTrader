# MANTIS — Binance Migration Wave Plan

## Date: 2026-05-06
## Status: planning — NOT YET STARTED. Replaces the abandoned Bybit
## migration track (`src/broker/bybit_client.py` stub will be deleted
## or repurposed; see Step 1).

---

## Scope

Migrate **crypto-only** trading from Capital.com CFDs to Binance
spot + perpetual futures. Capital.com remains the broker for forex,
indices, commodities, and equities. The platform runs **both brokers
concurrently** during and after the migration — there is no plan to
fully sunset Capital.com.

Initial Binance basket (mirrors Phase 0 KEEP crypto subset):

| Internal epic | Binance symbol | Market type | Wave |
|---------------|----------------|-------------|------|
| BTCUSD        | BTCUSDT        | USDT-M perp | 1    |
| ETHUSD        | ETHUSDT        | USDT-M perp | 1    |
| BNBUSD        | BNBUSDT        | USDT-M perp | 2    |

SOLUSD / DOGUSD / ICPUSD stay on Capital.com (Phase 0 EXCLUDE or
under-sized; revisit only if Wave 1+2 prove the cost-savings premise).

---

## Why Binance (vs staying Capital-only)

1. **Lower crypto fees**: Capital.com CFD spreads on BTCUSD widened
   to 4.2× the original Phase 3 cost assumption (memoised in
   `project_phase3_real_costs_2026-04-28.md`). Binance USDT-M perps
   charge 0.02 % maker / 0.05 % taker — under 1 bp round-trip on
   typical trade size.
2. **Native order types**: stop-market and trailing-stop are
   first-class on Binance, vs CFD-style stop_level + profit_level on
   Capital. Reduces rounding artefacts on partial-close ladder.
3. **L2 depth + funding rate**: opens the door to Phase 6 OFI track
   and funding-rate-aware sizing without paying for a third-party
   data feed.
4. **No Berlin-time quirks**: Binance returns ISO-8601 UTC strings;
   the `_normalize_broker_datetime` helper that papers over Capital
   Europe/Berlin naive timestamps is not needed.

---

## Pre-conditions (NONE OF WHICH ARE MET YET)

Migration starts only when ALL hold:

1. ✅ TSLA `_enforce_min_tp` bypass closed (`MIN_SIGNAL_RR_THRESHOLD`
   floor shipped 2026-05-06 — done).
2. ❌ LIVE deploy completed for ≥ 14 days on Capital.com per
   `PRODUCTION_LIVE_DEPLOY_PLAN.md` (need real broker-truth equity
   curve before changing brokers).
3. ❌ Binance account funded (separate USDT wallet, ≥ $5 000 to
   match crypto basket sizing without bumping into the $200
   `MIN_NOTIONAL_USD` floor on every position).
4. ❌ KYC + API key issued with **read-only initial scope** for soak
   period; `Trade` permission added only at Wave 1 cut-over.
5. ❌ 16 remaining pytest baseline failures triaged (do not start
   broker rework on a red baseline).

---

## Architecture overview

The seam already exists: `src/broker/protocol.py::BrokerClientProtocol`
defines the surface (`connect / list_positions / create_position /
close_position / modify_position / get_market_details / ...`).

Two violations of the seam to fix BEFORE writing the Binance client:

- `src/api/main.py:146` instantiates `CapitalComClient()` directly.
  Replace with a factory keyed on `BROKER_BACKEND` env (values:
  `capital`, `binance`, `mock`).
- `src/trading/paper_loop.py:22` imports `CapitalComClient`
  concretely. Replace import + type hints with
  `BrokerClientProtocol`. Capital-specific helpers (`EPIC_TO_BROKER`,
  Berlin-tz normaliser) move behind the concrete client.

Once those land, the Binance client is a drop-in alongside Capital;
both can run in the same process (one per asset class) — see Step 5
"Multi-broker routing".

### Files touched (whole wave)

```
NEW    src/broker/binance_client.py          # ~600-800 lines
NEW    src/broker/binance_websocket_client.py # ~250 lines (user data + market streams)
NEW    src/broker/factory.py                 # ~80 lines — BROKER_BACKEND dispatch
NEW    src/broker/binance_models.py          # Binance-specific dataclasses (FundingRate, OpenInterest)
NEW    src/broker/multi_broker_router.py     # routes by epic-class to the right concrete client
EDIT   src/broker/protocol.py                # add optional fundingRate(), openInterest() (typing.Protocol w/ runtime_checkable)
EDIT   src/broker/models.py                  # extend Position/Transaction models w/ optional Binance fields
EDIT   src/broker/__init__.py                # export factory + protocol
EDIT   src/api/main.py                       # use factory, NOT CapitalComClient()
EDIT   src/trading/paper_loop.py             # type-hint as BrokerClientProtocol
EDIT   src/utils/config.py                   # BINANCE_API_KEY / BINANCE_API_SECRET / BINANCE_TESTNET / BROKER_BACKEND
EDIT   src/api/system.py                     # /health reports per-broker status
EDIT   src/risk/risk_manager.py              # epic-class routing for fee model
EDIT   docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md  # supersedes Phase 4 Bybit ref
DELETE src/broker/bybit_client.py             # stub abandoned (or repurpose if useful)
NEW    tests/broker/test_binance_client.py   # protocol-conformance + sign-request unit tests
NEW    tests/integration/test_multi_broker_routing.py
```

---

## Wave 0 — Foundation (no real money)

Goal: protocol-conformant Binance stub + factory + multi-broker
router lands behind a feature flag. Does NOT trade real money.

### Steps

1. **Delete `bybit_client.py` stub** (or leave with a deprecation
   header pointing here — user choice). Keep `EPIC_TO_BYBIT_SYMBOL`
   as a reference if Binance reuses the same symbol pattern (it
   does for BTCUSDT / ETHUSDT / BNBUSDT).
2. **Add `BinanceClient` skeleton** matching `BrokerClientProtocol`.
   All methods raise `BinanceNotImplementedError` initially.
   Lifts the Bybit stub pattern verbatim (auth + URL constants +
   symbol mapping). Auth is HMAC-SHA256 with `timestamp` query
   param + `signature` query param per Binance Futures docs.
3. **Add `BinanceWebSocketClient`** for user-data stream
   (`/userDataStream` listenKey, 24h refresh) and per-symbol mark
   price + bookTicker streams. WS URL:
   `wss://fstream.binance.com/ws/<listenKey>` for private,
   `wss://fstream.binance.com/stream?streams=...` for market.
4. **Factory** in `src/broker/factory.py`:
   ```python
   def make_broker_client(backend: str) -> BrokerClientProtocol:
       if backend == "capital":  return CapitalComClient()
       if backend == "binance":  return BinanceClient()
       if backend == "mock":     return MockBroker()
       raise ValueError(f"Unknown BROKER_BACKEND={backend}")
   ```
5. **Replace direct instantiation** in `src/api/main.py:146` with
   `make_broker_client(settings.broker_backend)`. Default
   `BROKER_BACKEND=capital`.
6. **Multi-broker router** in `src/broker/multi_broker_router.py`:
   wraps two real concrete clients and dispatches per `epic`
   based on `BROKER_BACKEND_BY_CLASS` env (e.g.
   `crypto=binance,everything_else=capital`). Implements the same
   `BrokerClientProtocol`. **Initially disabled** — used only in
   Wave 1.
7. **Tests**: protocol-conformance test asserts `isinstance(client,
   BrokerClientProtocol)` for all three concrete clients (already
   passes for Capital/Mock; Binance stub satisfies it via raise
   stubs). Sign-request unit test against a fixed timestamp and
   secret to verify HMAC matches Binance examples.

### Done-when

- `pytest tests/broker/` green
- `BROKER_BACKEND=mock pytest tests/integration/` green
- Backend boots with `BROKER_BACKEND=binance` and reports a clean
  `/health` (no real API calls, just a successful client init)

### Estimated effort

3-4 days dev + 1 day test/doc.

---

## Wave 1 — BTCUSDT testnet soak

Goal: real Binance API integration on **testnet only**, with BTCUSDT
trading via the multi-broker router. Capital.com still authoritative
for everything else.

### Pre-flight (HARD-BLOCKERS)

- [ ] Wave 0 merged + 7 days clean on production (no regressions on
  Capital.com path)
- [ ] Binance testnet account created (`testnet.binancefuture.com`)
  with API key + secret stored in `.env.live` (NEVER committed)
- [ ] Funding-rate awareness understood: 8-hour funding cycle at
  00:00 / 08:00 / 16:00 UTC. Long + short pay funding rate
  bidirectionally; impacts overnight carry.
- [ ] `MAX_TOTAL_EXPOSURE` reviewed for the multi-broker case: the
  cap currently sums notional across all positions on the single
  broker. With two brokers, must sum across BOTH or risk doubling
  effective leverage.

### Steps

1. **Implement REST methods** on `BinanceClient`:
   - `connect` (validate creds via `GET /fapi/v2/account`)
   - `get_market_details` (`GET /fapi/v1/exchangeInfo` + cached
     symbol filters; `bookTicker` for snapshot bid/ask)
   - `get_historical_prices` (`GET /fapi/v1/klines`, max 1500/req,
     paginate)
   - `list_positions` (`GET /fapi/v2/positionRisk` — filter
     `positionAmt != 0`)
   - `create_position` (`POST /fapi/v1/order` w/ `MARKET`)
   - `modify_position` (Binance has no atomic SL+TP modify —
     emulate via cancel-and-replace of `STOP_MARKET` +
     `TAKE_PROFIT_MARKET` orders. Track linked deal_id internally.)
   - `close_position` (`POST /fapi/v1/order` w/ opposite side +
     `reduceOnly=true`)
   - `get_transaction_history` (`GET /fapi/v1/income?incomeType=
     REALIZED_PNL`) — for close-detection v2 SoT
   - `get_activity_history` (`GET /fapi/v1/userTrades`) — second
     authoritative source for the v2 close-detector
   - `get_accounts` (single synthetic Account from `positionRisk`
     + `balance` endpoints)
2. **Implement user-data WS**: position-update + order-update
   streams keep MANTIS in sync without polling. listenKey refresh
   every ~60 min via background task (similar to Capital.com session
   refresh). Mirror the existing `broker_ws._quote_listeners`
   fan-out so the 60s P&L snapshot system reads Binance prices the
   same way.
3. **Map epics + dealId**: Binance `orderId` (int) is not a UUID —
   wrap as `f"BIN-{symbol}-{orderId}"` so the existing close-detector
   3-tier match logic can work without schema changes.
4. **Binance close-detection**: `orderUpdate` WS event with
   `executionType=TRADE` + `status=FILLED` is the primary close
   signal. `realizedPnl` field on the user-trade entry replaces
   Capital.com's `Transaction.size` for the TRADE row P&L source.
   Tier 1 dealId match works as-is.
5. **Multi-broker router config**: enable
   `BROKER_BACKEND_BY_CLASS=crypto:binance,default:capital`. BTCUSDT
   routes to Binance, everything else to Capital.
6. **Risk-manager epic-class routing**: fee model now picks per
   broker (Capital spread vs Binance maker/taker). Add
   `BinanceFeeModel` alongside the implicit Capital one.

### Done-when

- 14-day testnet soak with BTCUSDT-only trades on Binance
- Capital.com volume on the other 9 KEEP epics unchanged
- 0 unreconciled close events from either broker
- Equity sync across both broker accounts visible in `/health` and
  dashboard
- Funding rate accrual visible in trade audit drawer (new section
  alongside swap)

### Estimated effort

8-12 days dev + 14 days testnet soak.

---

## Wave 2 — Mainnet cut-over

Goal: switch BTCUSDT, ETHUSDT, BNBUSDT to **real-money Binance
USDT-M perps**. Capital.com still authoritative for everything else.

### Pre-flight

- [ ] Wave 1 testnet soak ≥ 14 days, 0 reconciler regressions
- [ ] Binance mainnet KYC complete + USDT funded (≥ $5 000)
- [ ] API key with `Trade` permission, IP-allowlisted to backend
  static IP
- [ ] `BROKER_BACKEND_BY_CLASS=crypto:binance,default:capital`
  flipped via env (no code change needed thanks to Wave 0 factory)
- [ ] Daily P&L variance test: 7-day testnet equity curve vs
  Capital.com BTCUSDT phantom-trade (replay) variance < 30 %
- [ ] LIVE Capital.com track record ≥ 30 days (Phase 6 gate also
  requires ≥ 90 days, but Wave 2 starts earlier — OK because the
  Binance side has its own 14-day testnet soak)

### Steps

1. Flip env, restart backend, monitor 1h on `/health`.
2. Force a $50 manual smoke trade (BTCUSDT 0.001) via the Binance
   web UI; verify MANTIS picks up `positionUpdate` and writes a
   matching `paper_positions` row with the BIN-prefixed dealId.
3. Close the manual trade — verify trade audit shows it as a manual
   broker-side close, not an UNRECONCILED row.
4. Enable signal generation for BTCUSDT only; soak 24h with a
   single open position max, sized at 50 % of normal.
5. Day 2: lift size cap to 100 %.
6. Day 3-7: enable ETHUSDT.
7. Day 8: enable BNBUSDT.
8. Day 14: full Wave 2 sizing on all three crypto epics.

### Rollback

Same env-flip in reverse: `BROKER_BACKEND_BY_CLASS=` → falls back
to default Capital for crypto. Manual close any open Binance
positions on the Binance web UI before unwiring.

### Estimated effort

3-5 days dev (mainnet hardening — extra circuit-breaker on
Binance-specific error codes) + 14 days soak.

---

## Wave 3 — Funding-rate-aware sizing (Phase 6 unlock)

Goal: incorporate Binance funding rate into the sizing decision so
the strategy doesn't pay 0.05 % per 8h holding period to a position
the model is only mildly confident in.

This is gated behind Phase 6 trigger (3-month LIVE track record) per
`PHASE6_ADVANCED_ALPHA_PLACEHOLDER.md`. Documented here as
forward-context only.

### Approach (sketch)

- New feature `binance_funding_rate_8h` from
  `/fapi/v1/fundingRate`.
- Penalty in `KellySizer` when funding ≥ 0.05 % and predicted
  holding period ≥ 4h.
- Negative-funding bonus when the strategy is short on a
  positive-funding epic (collect funding while the trade plays out).

### Out of scope for this plan

- Spot trading on Binance (perps only)
- Cross-margin (start with isolated margin per position)
- Liquidation-heatmap features (Phase 6.1 separate track)
- L2 OFI features (Phase 6.3 separate track)

---

## Operational risks specific to Binance

1. **API key scope discipline**: the `Trade` permission cannot be
   limited per-symbol. A leaked key trades the entire account. IP
   allowlist + low-balance rule (keep ≤ 30 % of total crypto
   capital on Binance) mitigate.
2. **Geographic compliance**: Binance restricts certain countries
   (US users on `binance.us`, EU users on `binance.com` with
   regional sub-tenancy). Confirm the operating jurisdiction
   before mainnet.
3. **Funding-rate flips**: a previously-positive funding-rate epic
   can flip negative during a position; the sizing assumption
   becomes wrong mid-trade. Wave 3 addresses this; Waves 1-2
   accept the risk by capping max holding period to 4h on crypto.
4. **listenKey expiry**: 60-min refresh is hard — missing it
   silently breaks user-data stream. Treat listenKey-refresh
   failure as a Tier-1 alert (same severity as Capital
   `session_silent`).
5. **Maintenance windows**: Binance sometimes runs unannounced
   short maintenance. The reconciler dedicated 15s task already
   handles per-tick broker outages, but verify
   `RECONCILER_DEDICATED_ENABLED=true` stays on through the
   migration.

---

## Decision rule for keeping Binance

After Wave 2 + 30 days mainnet:

PASS (= keep Binance for crypto, plan Wave 3):
- Net P&L on the 3 crypto epics ≥ 1.20 × the same period's
  Capital.com BTCUSD P&L (extrapolated from the historical
  win-rate × the new lower fee structure)
- 0 missed close events on Binance side
- Funding-rate cost ≤ 0.10 % of average notional per 24h

FAIL (= revert to Capital.com for crypto, archive Binance code):
- Operational incidents (≥ 2 maintenance-driven manual
  interventions in 30 days)
- Net P&L on Binance crypto < 0.95 × phantom Capital.com baseline
- listenKey refresh failures > 1 / week

---

## What this plan does NOT cover

1. Migrating non-crypto assets (forex, equities, indices,
   commodities) to Binance — Binance does not list them in a
   reasonable form for this strategy.
2. Sunset of Capital.com — explicitly out of scope. The platform
   remains multi-broker indefinitely.
3. ANY change to the strategy layer, ML model retraining, or
   backtest engine — purely a broker-layer wave.
4. Phase 6 alpha tracks (liquidation, OFI, debate) — see
   `PHASE6_ADVANCED_ALPHA_PLACEHOLDER.md`.

---

## Roadmap pointer

`MANTIS_EVOLUTION_ROADMAP.md` Phase 4 currently references a
Bybit migration. Update the Phase 4 section to:

> **Phase 4 — Multi-broker (Binance crypto wave)**: see
> `docs/evolutive/BINANCE_MIGRATION_WAVE_PLAN.md`. Bybit track
> abandoned 2026-05-06.

