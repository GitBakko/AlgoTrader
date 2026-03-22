# Decision Audit Trail — Design Spec

**Date**: 2026-03-11
**Status**: Approved
**Approach**: Signal-centric (Approach A) — reuse existing `signals` table with JSONB `features`

## Overview

Every signal that reaches ScalpScore generates a structured audit record persisted to PostgreSQL. The record captures every decision point in the pipeline: ScalpScore votes, gate filter results, ML prediction, confidence tiering, risk management checks, and a market data snapshot. Both executed and rejected signals are logged. HOLD signals (no directional outcome) are NOT persisted to avoid volume bloat (~60K/day).

A slide-out drawer in the frontend displays the audit trail for any position or signal, accessible from all views where positions/signals are visible.

## Architecture Decision

**Approach A selected**: Single INSERT into the existing `signals` table per signal. The `features` JSONB column holds the full decision context. No new tables needed.

**Signal scope**: Only signals that reach the ScalpScore evaluation phase AND produce a BUY or SELL direction are logged. HOLD results and pre-filters (no model loaded, already has position, market closed, etc.) are NOT logged.

**Volume estimate**: With 21 epics evaluated every ~30 seconds, worst case is ~21 signals per iteration, but most will be HOLDs (not persisted). Typical volume: 5-15 EXECUTED + REJECTED signals per iteration, or ~15K-45K records/day at ~1-2KB each = ~15-90 MB/day.

---

## 1. Data Model

### 1.1 Existing `signals` Table (reused)

| Column | Type | Nullable | Usage |
|--------|------|----------|-------|
| `id` | int PK | no | Auto-increment |
| `epic` | str | no | Asset identifier |
| `timeframe` | str | no | "15min" (scalp) |
| `direction` | str | no | BUY / SELL (HOLD not persisted) |
| `confidence` | Decimal | no | Final confidence after all adjustments |
| `predicted_price` | Decimal | yes | Entry price |
| `stop_loss_price` | Decimal | yes | Calculated SL (null if rejected before risk) |
| `take_profit_price` | Decimal | yes | Calculated TP (null if rejected before risk) |
| `model_version` | str | no | `"scalp_score_v1"` for ScalpScore signals |
| `features` | JSONB | yes | **Full decision audit trail** (see 1.2) |
| `model_id` | FK→models | yes | Left null (ScalpScore is not a single ML model) |
| `strategy_id` | FK→strategies | yes | Left null (no strategies table populated) |
| `position_id` | FK→positions | yes | Linked when executed |
| `status` | str | no | EXECUTED / REJECTED (matching existing enum) |
| `generated_at` | datetime | no | Signal generation timestamp |
| `expires_at` | datetime | yes | Left null (signals don't expire in scalp mode) |

**Note on `rejection_reason`**: This column does NOT exist on the current `Signal` model. Rather than adding a migration, the rejection reason is stored inside the JSONB `features` field at `features.rejection_reason`. This avoids schema changes while keeping the data queryable via JSONB operators.

**Note on `model_version`**: This is a NOT NULL field. All ScalpScore signals use `"scalp_score_v1"` as the version string.

**Note on asyncpg timezone**: ALL `datetime` values written to this table MUST use `datetime.now(timezone.utc).replace(tzinfo=None)`. This is a project-wide requirement — asyncpg rejects timezone-aware datetimes with `TIMESTAMP WITHOUT TIME ZONE` columns.

### 1.2 JSONB `features` Schema

```json
{
  "version": 1,
  "rejection_reason": null,

  "votes": {
    "ema":        { "value": 1,  "ema_9": 2045.12, "ema_21": 2043.80 },
    "rsi":        { "value": -1, "rsi_14": 58.3 },
    "macd":       { "value": 1,  "histogram": 0.45, "macd": 1.23, "signal": 0.78 },
    "volume":     { "value": 1,  "volume": 15200, "volume_sma_20": 12100 },
    "adx":        { "value": 1,  "adx_14": 28.7 },
    "bb_keltner": { "value": -1, "bb_upper": 2052, "bb_lower": 2038, "kc_upper": 2050, "kc_lower": 2040, "bb_mid": 2045, "price": 2047.5 }
  },

  "gates": {
    "session":     { "passed": true,  "session_mult": 1.0, "utc_hour": 14, "zone": "kill_zone" },
    "dead_market": { "passed": true,  "adx": 28.7, "bb_width_pctile": 45 },
    "vwap":        { "passed": true,  "price": 2047.5, "vwap": 2044.0, "action": "none" },
    "htf":         { "passed": true,  "htf_bias": "bullish", "direction": "BUY", "enabled": true },
    "confluence":  { "passed": true,  "buy_votes": 4, "sell_votes": 1, "required": 3, "zone": "kill_zone" }
  },

  "ml": {
    "signal_class": 2,
    "signal_name": "BUY",
    "confidence": 0.72,
    "probabilities": { "SELL": 0.15, "HOLD": 0.13, "BUY": 0.72 },
    "agreement": "agree",
    "confidence_before": 0.67,
    "confidence_after": 0.67
  },

  "risk": {
    "approved": true,
    "rejection_reason": null,
    "circuit_breakers": { "ok": true, "tripped": [] },
    "sizing_method": "kelly",
    "kelly_fraction": 0.082,
    "position_size": 0.03,
    "confidence_tier": { "multiplier": 1.0, "tier": ">=0.65" },
    "equity_curve": { "multiplier": 1.0 },
    "correlation": { "multiplier": 0.85, "warnings": ["XAUUSD correlated with XAGUSD"] },
    "dynamic_sl": { "multiplier": 1.35, "baseline_atr": 12.5, "current_atr": 16.8, "vol_ratio": 1.34 },
    "stop_loss": 2035.0,
    "take_profit": 2060.0,
    "tp1": 2047.5,
    "tp2": 2060.0,
    "adjustments": ["correlation_0.85", "equity_curve_1.0"]
  },

  "market_snapshot": {
    "bid": 2047.3,
    "ask": 2047.7,
    "spread": 0.4,
    "atr": 16.8,
    "rsi": 58.3,
    "adx": 28.7,
    "regime": "trending",
    "bb_width": 14.0,
    "volume": 15200,
    "vwap": 2044.0,
    "htf_bias": "bullish"
  }
}
```

**`version` field**: Allows future schema evolution without breaking existing records.

**Partial JSONB for gate-rejected signals**: When a signal is rejected by a gate before reaching ML or risk checks, the JSONB will have `ml: null` and `risk: null`. Only `votes`, `gates`, and `market_snapshot` are guaranteed present. The `rejection_reason` at root level identifies which gate blocked.

**Example: session gate rejection**:
```json
{
  "version": 1,
  "rejection_reason": "session_blocked",
  "votes": { ... },
  "gates": {
    "session": { "passed": false, "session_mult": 0.0, "utc_hour": 22, "zone": "off_session" },
    "dead_market": null, "vwap": null, "htf": null, "confluence": null
  },
  "ml": null,
  "risk": null,
  "market_snapshot": { ... }
}
```

### 1.3 FK Linkage

- `signals.position_id` → linked when signal is executed and position is opened
- `positions.signal_id` → populated in `_persist_position_open()` for reverse lookup

Both FKs already exist in the models but are currently unpopulated. This feature wires them up.

---

## 2. Backend Pipeline — Capture Points

**Important**: Both `TradingSignal` and `RiskCheckResult` are **Pydantic BaseModels** (not dataclasses). Field additions use Pydantic conventions: `metadata: dict = Field(default_factory=dict)`. Mutations use `model_copy(update={...})` where immutability is needed.

### 2.1 ScalpScoreStrategy.generate_signal()

**File**: `backend/src/strategy/scalp_score_strategy.py`

**Change**: Add `metadata: dict` field to `TradingSignal` Pydantic model (default `Field(default_factory=dict)`). Populate it before every return path in `generate_signal()`:

- **Gate rejections** (session, dead market, confluence, HTF): metadata contains votes computed so far + the gate that blocked with `passed: false` + remaining gates as `null`
- **Signal returns** (BUY/SELL): metadata contains all 6 votes with underlying values + all gates with `passed: true` + market snapshot

Individual vote values (`ema_vote`, `rsi_vote`, etc.) are currently local variables. Each vote function is modified to return `(vote_value, detail_dict)` instead of just `vote_value`.

**Backtest note**: `generate_backtest_signals()` calls `generate_signal()` internally, so metadata will be populated during backtests too. This is acceptable overhead — the metadata dict is small and ephemeral (not persisted during backtests).

### 2.2 StrategyManager._process_scalp()

**File**: `backend/src/strategy/strategy_manager.py`

**Change**: After ML boost/halving, add `ml` section to `signal.metadata`. Since `_process_scalp()` already uses `model_copy()`, the metadata dict from `generate_signal()` is preserved through copies:

```python
signal.metadata["ml"] = {
    "signal_class": prediction.signal_class,
    "signal_name": prediction.signal_name,
    "confidence": prediction.confidence,
    "probabilities": prediction.probabilities,  # {"SELL": 0.15, "HOLD": 0.13, "BUY": 0.72}
    "agreement": agreement,           # "agree" | "neutral" | "disagree"
    "confidence_before": pre_ml_conf,
    "confidence_after": signal.confidence
}
```

### 2.3 RiskManager.check_trade()

**File**: `backend/src/risk/risk_manager.py`

**Change**: Add `audit: dict` field to `RiskCheckResult` Pydantic model (default `Field(default_factory=dict)`). Build it progressively during checks:

```python
result.audit = {
    "approved": True,
    "rejection_reason": None,
    "circuit_breakers": {"ok": ok, "tripped": list(tripped)},
    "sizing_method": sizing_method,
    "kelly_fraction": kelly_fraction,
    "position_size": size,
    "confidence_tier": {"multiplier": conf_mult, "tier": tier_name},
    "equity_curve": {"multiplier": eq_mult},
    "correlation": {"multiplier": corr_mult, "warnings": corr_warnings},
    "dynamic_sl": {"multiplier": sl_mult, "baseline_atr": baseline, "current_atr": current, "vol_ratio": ratio},
    "stop_loss": sl, "take_profit": tp, "tp1": tp1, "tp2": tp2,
    "adjustments": adjustments_list
}
```

For early rejections (circuit breaker, exposure cap, drawdown), the audit dict is still populated with the data available up to the rejection point, plus `"approved": false` and `"rejection_reason": "circuit_breaker"` (or relevant check name).

### 2.4 PaperTradingLoop._process_epic() — Assembly & Persistence

**File**: `backend/src/trading/paper_loop.py`

**Change**: After all pipeline stages complete, assemble the full JSONB and persist:

```python
# Assemble audit JSONB — explicit key construction (no ** splat to avoid collisions)
audit_features = {
    "version": 1,
    "rejection_reason": rejection_reason,  # None if executed, gate/check name if rejected
    "votes": signal.metadata.get("votes"),
    "gates": signal.metadata.get("gates"),
    "ml": signal.metadata.get("ml"),       # None if rejected before ML
    "risk": risk_result.audit if risk_result else None,
    "market_snapshot": signal.metadata.get("market_snapshot"),
}

# Insert into signals table
signal_id = await signal_repository.create(
    epic=epic, direction=signal.direction, confidence=signal.confidence,
    predicted_price=signal.entry_price,
    stop_loss_price=getattr(risk_result, 'stop_loss', None),
    take_profit_price=getattr(risk_result, 'take_profit', None),
    model_version="scalp_score_v1",
    features=audit_features,
    status="EXECUTED" if executed else "REJECTED",
    generated_at=datetime.now(timezone.utc).replace(tzinfo=None)
)

# On execution success: link position ↔ signal
await signal_repository.mark_as_executed(signal_id, position_id)
# In _persist_position_open(): set position.signal_id = signal_id
```

**`_signal_history` deque**: Remains as-is for the real-time `/api/trading/signals` endpoint. A `signal_db_id` field is added to the `signal_info` dict so the frontend can link in-memory signals to persisted records. The `_last_signals` dict also remains unchanged.

**Error handling**: If the DB INSERT fails (e.g., connection lost), the error is logged but does NOT block trade execution. The audit trail is best-effort — losing a signal record is acceptable; blocking a profitable trade is not.

---

## 3. API Endpoints

New router: `backend/src/api/routers/signals.py`

### 3.1 GET /api/signals/{signal_id}

Returns the full signal record with JSONB features and position summary.

**Response**:
```json
{
  "success": true,
  "data": {
    "id": 42,
    "epic": "XAUUSD",
    "direction": "BUY",
    "confidence": 0.67,
    "status": "EXECUTED",
    "generated_at": "2026-03-11T14:23:00Z",
    "rejection_reason": null,
    "features": { "version": 1, "votes": {...}, "gates": {...}, "ml": {...}, "risk": {...}, "market_snapshot": {...} },
    "position_summary": {
      "deal_id": "DEAL-123",
      "entry_price": 2047.5,
      "current_price": 2052.3,
      "pnl": 14.40,
      "pnl_pct": 0.23,
      "stop_loss": 2035.0,
      "take_profit": 2060.0,
      "status": "OPEN",
      "close_reason": null,
      "opened_at": "2026-03-11T14:23:01Z",
      "closed_at": null,
      "size": 0.03
    }
  }
}
```

- `position_summary` is `null` when `status != EXECUTED`
- `features.rejection_reason` contains the rejection reason for REJECTED signals
- For open positions: `current_price` is the last price from `PaperTradingLoop._last_prices` cache (same source as the positions endpoint)
- For closed positions: `current_price` = `exit_price` from the `positions` table

**Error responses**:
- Signal not found: `{"success": false, "error": "Signal not found"}` with HTTP 404
- Server error: `{"success": false, "error": "Internal error"}` with HTTP 500

### 3.2 GET /api/signals/by-position/{deal_id}

Shortcut: given a `deal_id`, returns the linked signal's full audit. Same response shape as 3.1.

Lookup: `SELECT * FROM signals WHERE position_id = (SELECT id FROM positions WHERE deal_id = :deal_id ORDER BY opened_at DESC LIMIT 1) ORDER BY generated_at DESC LIMIT 1`.

If no signal is linked (positions opened before this feature was deployed), returns `{"success": true, "data": null}`.

### 3.3 GET /api/signals/history/{epic}?limit=10&offset=0

Last N signals for an epic with pagination. Lightweight response (no JSONB features):

```json
{
  "success": true,
  "data": [
    {
      "id": 42,
      "epic": "XAUUSD",
      "direction": "BUY",
      "confidence": 0.67,
      "status": "EXECUTED",
      "generated_at": "2026-03-11T14:23:00Z",
      "rejection_reason": null,
      "position_pnl": 14.40,
      "position_status": "OPEN"
    }
  ],
  "total": 156
}
```

- `rejection_reason` is extracted from `features->'rejection_reason'` via JSONB operator
- `position_pnl` and `position_status` come from a LEFT JOIN on `positions`
- `total` enables pagination in the frontend if needed
- Clicking a row in the frontend calls GET /api/signals/{id} for the full detail

### 3.4 Live Refresh

No new WebSocket endpoint. Open position P&L is recalculated client-side using `WebSocketService.prices()` — the same pattern already used in Paper Trading, Positions, and Dashboard views.

---

## 4. Frontend — Signal Audit Drawer

### 4.1 Component Architecture

```
shared/components/signal-audit-drawer/
├── signal-audit-drawer.component.ts      # Main drawer with slide animation
├── signal-audit-drawer.component.html    # Template
└── signal-audit-drawer.component.scss    # Styles (CSS custom props, no @use "palette")

core/services/
└── signal-audit.service.ts               # API calls, cache, open/close state

core/models/index.ts                      # New interfaces: SignalAudit, SignalHistoryItem
```

### 4.2 SignalAuditService

```typescript
@Injectable({ providedIn: 'root' })
export class SignalAuditService {
  // State
  isOpen = signal(false);
  currentAudit = signal<SignalAudit | null>(null);
  relatedSignals = signal<SignalHistoryItem[]>([]);
  loading = signal(false);

  // Actions
  open(signalId: number): void;           // GET /api/signals/{id} + GET /api/signals/history/{epic}
  openByDealId(dealId: string): void;     // GET /api/signals/by-position/{dealId} + history
  close(): void;
  navigateToSignal(signalId: number): void;  // Replace drawer content
}
```

### 4.3 Drawer Component

- **Placement**: Rendered in `DefaultLayoutComponent` (global, always available)
- **Width**: 480px on desktop (xl+), 100% on mobile (<768px)
- **Animation**: `translateX(100%)` → `translateX(0)`, 250ms ease-out
- **Backdrop**: `rgba(0,0,0,0.5)`, click to close
- **Close**: ✕ button, ESC key (`@HostListener`), backdrop click
- **Scroll**: Body scrollable, header sticky
- **Z-index**: 1040 (below CoreUI modals at 1050)
- **Focus trap**: Implemented in Phase 2 (not deferred to Phase 3) — a drawer without focus trap leaks keyboard navigation

### 4.4 Drawer Sections (top to bottom)

1. **Header (sticky)**: Epic logo + name, direction badge (BUY green / SELL red), timestamp, status badge (EXECUTED green / REJECTED red), close button

2. **Position Summary Card**: Border-left colored (green profit / red loss). Grid 3×2: entry, current/exit price, P&L (with %), size, SL, TP. For open positions: pulsing LIVE indicator, P&L updates via WebSocket. For closed: close reason badge, final P&L, duration. **Hidden entirely for REJECTED signals** (no position exists) — replaced with a compact "Segnale rifiutato: {reason}" banner.

3. **ScalpScore Votes**: Section header with diamond icon + "4/6 BUY" badge. Grid rows: indicator name (80px), vote value colored (+1 green, −1 red, 0 neutral), underlying data in mono font.

4. **Gate Filters**: Section header + "5/5 passed" counter. Each gate: green/red dot, gate name (90px), detail text. Failed gates show red dot + explanation. Gates that were not reached (downstream of a blocking gate) show grey dot + "Non valutato".

5. **ML Prediction**: Three probability boxes (SELL red / HOLD amber / BUY green), dominant class highlighted with border. Agreement badge (AGREE green / NEUTRAL amber / DISAGREE red). Confidence before → after. **Hidden if `features.ml` is null** (signal rejected before ML phase) — shows "ML non raggiunto" placeholder.

6. **Risk Management**: 2-column grid of key-value pairs: sizing method, Kelly %, confidence tier, equity curve mult, correlation mult, dynamic SL mult. Warning callout at bottom for correlation warnings. Long warning text uses `word-break: break-word` to handle overflow in the 480px width. **Hidden if `features.risk` is null** (signal rejected before risk phase) — shows "Risk check non raggiunto" placeholder.

7. **Related Signals (Phase 3)**: Section header "Ultimi Segnali {EPIC}". Compact list: time, direction, confidence, status badge, P&L or rejection reason. Current signal highlighted with green left border. Click → `navigateToSignal(id)`.

### 4.5 TypeScript Interfaces

```typescript
interface SignalAudit {
  id: number;
  epic: string;
  direction: 'BUY' | 'SELL';
  confidence: number;
  status: 'EXECUTED' | 'REJECTED';
  generated_at: string;
  rejection_reason: string | null;       // from features.rejection_reason
  features: SignalFeatures;
  position_summary: PositionSummary | null;  // null for REJECTED
}

interface SignalFeatures {
  version: number;
  rejection_reason: string | null;
  votes: Record<string, { value: number; [key: string]: any }>;
  gates: Record<string, { passed: boolean; [key: string]: any } | null>;  // null = not evaluated
  ml: SignalMl | null;                   // null if rejected before ML
  risk: SignalRisk | null;               // null if rejected before risk
  market_snapshot: Record<string, number | string>;
}

interface SignalMl {
  signal_class: number;
  signal_name: string;
  confidence: number;
  probabilities: Record<string, number>;
  agreement: string;
  confidence_before: number;
  confidence_after: number;
}

interface SignalRisk {
  approved: boolean;
  rejection_reason: string | null;
  circuit_breakers: { ok: boolean; tripped: string[] };
  sizing_method: string;
  kelly_fraction: number;
  position_size: number;
  confidence_tier: { multiplier: number; tier: string };
  equity_curve: { multiplier: number };
  correlation: { multiplier: number; warnings: string[] };
  dynamic_sl: { multiplier: number; baseline_atr: number; current_atr: number; vol_ratio: number };
  stop_loss: number;
  take_profit: number;
  tp1: number;
  tp2: number;
  adjustments: string[];
}

interface PositionSummary {
  deal_id: string;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_pct: number;
  stop_loss: number;
  take_profit: number;
  status: 'OPEN' | 'CLOSED';
  close_reason: string | null;
  opened_at: string;
  closed_at: string | null;
  size: number;
}

interface SignalHistoryItem {
  id: number;
  epic: string;
  direction: 'BUY' | 'SELL';
  confidence: number;
  status: 'EXECUTED' | 'REJECTED';
  generated_at: string;
  rejection_reason: string | null;
  position_pnl: number | null;
  position_status: string | null;
}
```

### 4.6 Integration Points

| View | Element | Trigger | Method |
|------|---------|---------|--------|
| Paper Trading | Position detail row (expanded group) | `(click)` on row | `openByDealId(pos.deal_id)` |
| Paper Trading | Signal feed row | `(click)` on row | `open(signal.signal_db_id)` |
| Positions (Open) | Position table row | `(click)` on row (not Close btn) | `openByDealId(pos.deal_id)` |
| Positions (History) | Closed position row | `(click)` on row | `openByDealId(pos.deal_id)` |
| Dashboard | Mini positions table row | `(click)` on row | `openByDealId(pos.deal_id)` |
| Trade Journal | Signal table row | `(click)` on row | `open(signal.signal_db_id)` |

**Click conflict resolution**: Action buttons (Close position, note editor) use `$event.stopPropagation()` to prevent the row click from also opening the drawer.

**Linking in-memory signals to DB records**: A `signal_db_id: number | null` field is added to the `signal_info` dict in `_process_epic()` and to the `PaperSignal` TypeScript interface. This is the DB `signals.id` returned after INSERT. For signals from before this feature, `signal_db_id` is null — the click handler shows a "Audit non disponibile per segnali precedenti" toast.

---

## 5. Phased Rollout

### Phase 1: Backend Logging (no UI changes)

1. Add `metadata: dict` field to `TradingSignal` Pydantic model (`Field(default_factory=dict)`)
2. Modify vote functions in `ScalpScoreStrategy` to return `(value, details)` tuples
3. Populate `signal.metadata` with votes + gates + market_snapshot in `generate_signal()`
4. Add ML section to `signal.metadata` in `StrategyManager._process_scalp()`
5. Add `audit: dict` field to `RiskCheckResult` Pydantic model, populate during `check_trade()`
6. In `_process_epic()`: assemble full JSONB, INSERT into `signals` table via `SignalRepository`
7. Link `signal_id` ↔ `position_id` on execution
8. Add `signal_db_id` to `signal_info` dict for frontend linkage
9. Create signals API router with 3 endpoints
10. Unit tests for logging pipeline + API endpoints

**Deliverable**: Decision data captured and queryable via API. No frontend changes.

### Phase 2: Frontend Drawer

1. Create `SignalAuditService` with open/close state and API methods
2. Create `SignalAuditDrawerComponent` (shared) with sections 1-6 (except related signals)
3. Add drawer to `DefaultLayoutComponent`
4. Add TypeScript interfaces (`SignalAudit`, `SignalFeatures`, `SignalMl`, `SignalRisk`, `PositionSummary`, `SignalHistoryItem`)
5. Wire click handlers in all 6 views
6. Live P&L refresh via WebSocket for open positions
7. Mobile responsive (100% width below 768px)
8. Focus trap + ESC key handler
9. Handle null `ml` and `risk` sections gracefully (placeholder text)

**Deliverable**: Fully functional audit drawer on all views.

### Phase 3: Related Signals + Polish

1. Add "Ultimi Segnali" section to drawer (calls GET /api/signals/history/{epic})
2. Click-to-navigate between related signals (replaces drawer content, no stacking)
3. Current signal highlighted with green left border
4. Slide animation polish
5. `prefers-reduced-motion` support

**Deliverable**: Complete feature with signal navigation.

---

## 6. Design Tokens & Styling

All styles follow MANTIS AI design system. Component SCSS uses CSS custom properties only (no `@use "palette"`).

- Surface: `var(--mantis-surface-2)` for drawer bg, `var(--mantis-surface-3)` for cards
- Borders: `var(--mantis-border-default)` for drawer left edge, `var(--mantis-border-subtle)` for inner dividers
- Text: `var(--cui-body-color)` for values, `var(--cui-secondary-color)` for labels
- Numbers: `font-family: 'IBM Plex Mono', monospace` (directly, since `--mantis-font-mono` may not be a CSS variable)
- Profit: `var(--mantis-profit)` (#39FF14)
- Loss: `var(--mantis-loss)` (#FF3D57)
- Warning: `var(--mantis-warning)` (#FFB020)
- Neutral: `#8B949E` (hardcoded, as it's a fixed neutral regardless of theme)
- Section icon accent: `#00E5FF` (hardcoded cyan, used only for small diamond icons)

**Note**: Verify which MANTIS design tokens are exposed as CSS custom properties vs SCSS-only variables. For any token not available as `var(--...)`, use the hardcoded value with a comment referencing the SCSS source.

---

## 7. Testing Strategy

### Backend
- Unit tests for vote function return shape (`(value, details)` tuples)
- Unit test for `generate_signal()` metadata completeness (all keys present for BUY/SELL, partial for gate rejections)
- Unit test for `_process_scalp()` ML section
- Unit test for `check_trade()` audit dict (both approved and rejected paths)
- Integration test: full pipeline from `_process_epic()` → INSERT → verify JSONB in DB
- API tests for all 3 endpoints (happy path + 404 not found + empty history + null signal link)
- Edge case: `features` is null or malformed → API returns graceful error, not 500
- Edge case: position opened before feature deployment → `by-position` returns `data: null`
- Performance: verify INSERT does not add >5ms to `_process_epic()` critical path

### Frontend
- Component test: drawer opens/closes with animation
- Component test: renders all sections from mock data (full JSONB)
- Component test: renders correctly when `ml` and `risk` are null (rejected signal)
- Service test: `open()` and `openByDealId()` call correct endpoints
- Service test: `openByDealId()` with null response shows toast
- Integration test: click on position row → drawer opens with correct data
- Focus trap: keyboard navigation stays within drawer when open
