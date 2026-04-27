# HANDOFF · Paper Trading — Variant B (Ambitious)

**Target:** sostituzione diretta del componente `paper-trading` esistente con la v2 Variant B.
**Stack:** Angular 21 (signals + standalone components) · CoreUI 5 · SCSS · IBM Plex Mono + Plus Jakarta Sans.
**Repo:** `GitBakko/AlgoTrader` · branch `main`.

> **Prerequisito di lettura:** [`STYLE_BIBLE.md`](./STYLE_BIBLE.md). Le regole `CARD-*`, `HDR-*`, `TBL-*`, `BTN-*`, `CHIP-*`, `FRM-*`, `KPI Pattern`, `Mini Charts`, `Timeline / Live Feed`, `VIO-*` sono **vincolanti**.

---

## 1 · Cosa stai costruendo

Una **cockpit dashboard live** per il Paper Trading Bot, organizzata in 3 colonne. La pagina sostituisce l'attuale `frontend/src/app/views/paper-trading/` (vista flat dense con tabella sotto KPI piatti).

### 1.1 Layout — 3 colonne

```
┌────────────── HDR-01 Cockpit Header ──────────────────────┐
│ ▼ MANTIS · Paper Trading  ● RUNNING  DEMO     [STOP] [✕]  │
├──────────┬───────────────────────────────┬────────────────┤
│ LEFT     │ CENTER                        │ RIGHT          │
│ 260px    │ 1fr (flex)                    │ 360px          │
│          │                               │                │
│ Bot      │ KPI Strip (compact, 6 cells)  │ Live Feed      │
│ Vitals   │                               │ Timeline       │
│          │ Active Positions Cockpit      │                │
│ Risk     │  (1+ position cards)          │ (sticky,       │
│ Gauges   │                               │  scrolls       │
│          │ Signals Heatmap (21 cells)    │  internally)   │
│ Models   │                               │                │
│ Health   │                               │                │
│          │                               │                │
└──────────┴───────────────────────────────┴────────────────┘
                       Footer (build, latency)
```

Padding outer 14px, gap colonne 12px, gap interno colonna 10-12px.

### 1.2 Decisioni fissate (dal Q&A)

- **Densità default:** compact
- **Drawer dettaglio posizione:** width **380px** (espandibile a 440 dense)
- **Modalità:** Mantis Bot (default) · Broker · No-protect (toggle in header secondary, future)
- **Una sola Variant in produzione:** B (Ambitious). Variant A va archiviata, NON committata.

---

## 2 · File system del repo

### 2.1 Cartella target
```
frontend/src/app/views/paper-trading/
├── paper-trading.component.ts
├── paper-trading.component.html
├── paper-trading.component.scss
├── paper-trading.routes.ts
├── components/
│   ├── cockpit-header/                 ← HDR-01 (esiste in dashboard-v2, riusa o estrai a shared)
│   ├── bot-vitals-panel/               ← left rail · heartbeat ECG + iter/uptime/errors + signals donut
│   ├── risk-gauge-stack/               ← left rail · 4 gauges (CB · Equity Filter · Kelly · Trading Stops)
│   ├── models-health-panel/            ← left rail · models loaded indicator + per-asset bullets
│   ├── kpi-strip-compact/              ← center · 6 KPI cells (P&L Open · P&L Today · Open · Win/Sig · R:R · DD)
│   ├── active-positions-cockpit/       ← center · large position cards stack
│   ├── position-card/                  ← reusable rich card (CARD-03)
│   ├── signals-heatmap/                ← center · 21-cell mosaic per-asset
│   ├── live-feed-timeline/             ← right rail · activity stream
│   └── position-detail-drawer/         ← MDL-02 drawer (future-ready, non bloccante per il primo PR)
└── services/
    └── paper-trading.service.ts        ← interfaccia con backend (vedi §6)
```

> **Convenzione:** ogni sub-component è **standalone** (`standalone: true`) con `ChangeDetectionStrategy.OnPush`.

### 2.2 SCSS scope

Stili specifici nel file SCSS del component (non globali). I colori vengono **solo** da `_palette.scss` via `@use '../../../scss/palette' as p`. **Mai** hex hardcoded — se vedi `#39FF14`, sostituiscilo con `p.$mantis-neon`.

---

## 3 · Componenti — spec dettagliata

Ogni componente ha: **scopo · input · output · regole Style Bible applicabili · note implementative**.

### 3.1 `cockpit-header`
**Scopo:** HDR-01. Riusabile tra Dashboard e Paper Trading.
**Input:**
- `pageTitle: string` (es. `'Paper Trading'`)
- `state: 'RUNNING' | 'IDLE' | 'ERROR'`
- `mode: 'DEMO' | 'LIVE'`
- `marketStatus: 'OPEN' | 'CLOSED' | 'PRE'`
- `lastTickAgo: number` (secondi)
- `actions: { stop: () => void; emergency: () => void }`

**Output:** `(stopClicked)` `(emergencyClicked)` (preferito a callback in input).

**Style Bible:** HDR-01 + CHIP-01 (status pill RUNNING/DEMO con dot pulsante) + BTN-warning (STOP) + BTN-danger (EMERGENCY).
**Note:** se è già implementato per Dashboard v2, **estrai in `shared/components/cockpit-header/`** e referenzialo.

---

### 3.2 `bot-vitals-panel`
**Scopo:** indicatore visivo "il bot è vivo" + metriche operative compatte.
**Sezioni interne (nell'ordine):**
1. Header: dot pulsante verde + label `BOT VITALS` (CHIP-01 style)
2. **Heartbeat ECG** (48px alto): SVG polyline animata con stroke `--mantis-neon`. La forma simula un cardiotracciato. Glow `drop-shadow(0 0 4px rgba(57,255,20,0.6))`. In sovrimpressione: `lastTickAgo` (es. `1.2s`)
3. Stat grid 2×2: `ITER`, `INTERVAL`, `UPTIME`, `ERRORS` (mono, 9px label + 16px value)
4. Signals Donut: SVG donut 56px con tre slice (executed verde · rejected rosso · hold neutro). A destra: `64 / 2` (total / executed) + `conv 3.7%` cyan

**Input:**
```ts
interface BotVitals {
  state: 'RUNNING' | 'IDLE' | 'ERROR';
  uptime: string;            // "4h 12m"
  lastTickAgo: number;       // 1.2
  iterations: number;        // 9
  intervalSec: number;       // 900
  errors: number;            // 0
  signals: { total: number; executed: number; rejected: number; hold: number; conversion: number };
}
```

**Style Bible:** CHIP-01 · KPI Pattern (per i 4 stat) · Mini Charts (donut e ECG).
**Animazione ECG:** se preferisci SVG statico è ok per il primo PR; v1.1 → animazione `stroke-dashoffset` per simulare scrittura continua del tracciato.

---

### 3.3 `risk-gauge-stack`
**Scopo:** sintesi del Risk Manager — 4 gauge in colonna.
**4 gauge (ognuno una row):**
1. **Circuit Breakers** — stato OK/WARN/ERROR + `0/6 tripped`
2. **Equity Filter** — `DD 19.4% / 20%` — barra orizzontale con threshold marker
3. **Kelly Sizing** — stato ATTIVO/PAUSED + `avg 14 · win 60.4% · pnl -28.7`
4. **Trading Stops** — stato OK + count

Ogni gauge è un mini-pannello con border-left 3px del color stato (CARD-03), header micro label + value mono, opzionale barra/sparkline sotto.

**Input:**
```ts
interface RiskState {
  circuitBreakers: { status: Status; tripped: number; total: number };
  equityFilter:    { status: Status; dd: number; threshold: number };
  kelly:           { status: Status; avg: number; win: number; pnl: number };
  tradingStops:    { status: Status; count: number };
}
type Status = 'OK' | 'WARN' | 'ATTIVO' | 'ERROR' | 'PAUSED';
```

**Style Bible:** CARD-03 · CHIP-01.

---

### 3.4 `models-health-panel`
**Scopo:** "Tutti i modelli AI caricati e operativi?"
**Contenuto:**
- Header `MODELS` mono uppercase + valore `21/21` (loaded/total) verde
- Sotto: bullet grid 7×3 con un dot per asset (verde=ok, rosso=missing, ambra=stale).

**Input:** `{ loaded: number; total: number; perAsset: Array<{epic, status: 'ok'|'missing'|'stale'}> }`

**Style Bible:** CARD-02 (border-top verde) · KPI Pattern.

---

### 3.5 `kpi-strip-compact`
**Scopo:** 6 KPI cells in fila orizzontale, max altezza 84px.
**Cells (ordinati):**
1. **P&L Open** — verde/rosso, valore unrealized
2. **P&L Today** — verde/rosso, valore realized chiuso oggi
3. **Open Positions** — bianco, count
4. **Win Rate / Signals** — `60.4% · 64sig`, dual line
5. **R:R Avg** — `1:1.94` cyan
6. **DD Live** — `−1.2% · gate 20%` con barra mini

Ogni cell: CARD-02 (border-top color categoria), micro label + value 22px mono, sparkline opzionale absolute top-right per cells 1-2.

**Input:**
```ts
interface KpiStrip {
  pnlOpen: number; pnlToday: number;
  openCount: number;
  winRate: number; signalsTotal: number;
  rr: number;
  ddLive: number; ddGate: number;
  sparkOpen?: number[]; sparkToday?: number[];
}
```

**Style Bible:** CARD-02 · KPI Pattern · Mini Charts.

---

### 3.6 `active-positions-cockpit` + `position-card`
**Scopo:** stack verticale di card ricche, una per posizione aperta. **Componente core della pagina.**

#### `position-card` — i 7 campi obbligatori per ogni posizione
1. **Entry value** (prezzo di apertura)
2. **Stop Loss** (prezzo + distanza in % e in valuta)
3. **Take Profit** (prezzo + distanza in % e in valuta)
4. **Trend** (sparkline 1H del prezzo dall'entry, color = direction)
5. **Age** (uptime posizione, mono compact)
6. **Trailing** (CHIP-02 `TRAIL ON` cyan / `TRAIL OFF` neutral)
7. **Current value** (prezzo corrente + P&L unrealized in valuta + %)

#### Layout della card
- CARD-03 con `border-left: 3px solid <pnlColor>` (verde se profit, rosso se loss)
- Padding 12px, radius 6px
- Header row: ticker mono 700 18px · CHIP-03 direction · CHIP-02 size lots · spacer · CHIP-02 AGE
- Body grid 5 colonne: Entry · SL · TP · Current · Trend
- Footer row: P&L valore + % · CHIP-02 TRAIL · CHIP-02 R:R · spacer · button ghost "Dettagli" (apre Drawer)

**Input:**
```ts
interface Position {
  id: string;
  ticker: string;          // 'USDJPY'
  direction: 'BUY' | 'SELL';
  size: number;            // lots
  entry: number;
  stopLoss: number;
  takeProfit: number;
  current: number;
  pnlEur: number;
  pnlPct: number;
  ageSec: number;          // 1620 → '27m'
  trailing: boolean;
  rr: number;              // 1.94
  pricePath: number[];     // 60 punti per sparkline
}
```

**Output:** `(detailsClicked: Position)`.

**Style Bible:** CARD-03 · CHIP-02/03 · KPI Pattern · Mini Charts · BTN-ghost.
**Empty state:** se 0 posizioni aperte, mostra `EmptyState` con icona binocolo + testo `Nessuna posizione aperta · il bot sta osservando ${signals.total} segnali`.

---

### 3.7 `signals-heatmap`
**Scopo:** 21-cell mosaic per-asset, una "TV" del comportamento del bot ora.

**Layout:** grid 7×3 (o 21 chip rounded, gap 6px). Ogni cell:
- Background tinted (rgba 8%) del color direzione (BUY=green, SELL=red, HOLD=neutral)
- Border tinted 25%
- Mono 9px ticker (alto-sx) + mono 11px direction (centro) + state badge (bottom-right) `live/closed/rejected/hold`
- Click → focus drawer con audit segnale

**Input:**
```ts
interface AssetSignal {
  epic: string;            // 'XAUUSD'
  direction: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;      // 0-100
  state: 'live' | 'closed' | 'rejected' | 'hold';
  time: string;            // '06:24'
}
```

**Style Bible:** CHIP-03 · Mini Charts (ogni cella è un micro-pannello).

---

### 3.8 `live-feed-timeline`
**Scopo:** stream verticale degli eventi recenti del bot. Sticky column right.

**Composizione:**
- Header sticky: dot pulsante verde + `LIVE FEED` mono uppercase + count `64` events
- Lista verticale (timeline pattern §2.3 della Bible): timestamp 60px fixed mono 10px white/40 → dot color stato → contenuto
- Tipi di evento: `iteration` (verde), `signal-emit` (cyan), `signal-reject` (rosso), `position-open` (verde bold), `position-close` (rosso/verde), `error` (rosso), `model-load` (neutral)
- Ogni row: 1 line title mono 11px · 1 line meta mono 9px white/40
- Auto-scroll opzionale (toggle pin in alto)

**Input:** `{ events: Array<{id, ts, kind, title, meta}>; maxRows?: number }`

**Style Bible:** Timeline / Live Feed (§2.3) · CHIP-01.

---

### 3.9 `position-detail-drawer`
**Scopo:** MDL-02 — drawer right-side 380px con dettagli profondi della posizione (open audit, trade history, model reasoning).
**Stato:** **future-ready, non bloccante per il primo PR.** Crea il componente vuoto con header + close button + tab strip (`Overview · Audit · History`); body placeholder.

**Style Bible:** MDL-02.

---

## 4 · SCSS — pattern di partenza

```scss
// paper-trading.component.scss
@use '../../../scss/palette' as p;
@use 'sass:color';

:host {
  display: block;
  height: 100%;
  background: p.$mantis-surface-1;
  font-family: var(--mantis-font-ui);
  color: #fff;
}

.pt-grid {
  display: grid;
  grid-template-columns: 260px 1fr 360px;
  gap: 12px;
  padding: 14px;

  @media (max-width: 1280px) {
    grid-template-columns: 220px 1fr 320px;
  }

  @media (max-width: 1080px) {
    grid-template-columns: 1fr;
    .pt-rail-right { order: 3; }
  }
}

.pt-card {
  background: p.$mantis-surface-2;
  border: 1px solid rgba(p.$mantis-green, .15);
  border-radius: 6px;
  padding: 12px;

  &--accent-neon { border-top: 2px solid p.$mantis-neon; }
  &--accent-cyan { border-top: 2px solid p.$mantis-cyan; }
  &--accent-loss { border-top: 2px solid p.$mantis-loss; }

  &--state-profit { border-left: 3px solid p.$mantis-neon; }
  &--state-loss   { border-left: 3px solid p.$mantis-loss; }
  &--state-trail  { border-left: 3px solid p.$mantis-cyan; }
}
```

---

## 5 · Mock React — referenza visiva

I file `.jsx` in `mocks/` sono **specifica visiva**, non da committare nel repo Angular. Replicano stile e dati che il componente Angular deve riprodurre 1:1.

```
mocks/
├── index.html               ← wrapper design canvas
├── design-canvas.jsx
├── Shared.jsx               ← mock data (PAPER_STATE, RISK_STATE, ASSET_UNIVERSE, LAST_SIGNALS, POSITIONS)
├── CockpitHeader.jsx
├── PositionCard.jsx
├── SignalsAndFeed.jsx       ← SignalsHeatmap + LiveFeedTimeline
└── VariantB_Ambitious.jsx   ← layout master della pagina
```

**Apri `mocks/index.html`** → Variant B (Ambitious). Quello è il pixel-target.

---

## 6 · Backend / data contract

Il componente esistente legge da `paper-trading.service.ts`. Verifica che l'interfaccia copra **tutti** i 7 campi posizione + `signals` distribution + `risk` state.

### 6.1 Endpoint richiesti (verifica esistenza, altrimenti crea)

| Endpoint | Method | Returns | Note |
|---|---|---|---|
| `/api/paper/state` | GET | `{ status, uptime, iterations, errors, lastTick, signals }` | refresh ogni 5s |
| `/api/paper/positions/open` | GET | `Position[]` | refresh ogni 2s |
| `/api/paper/risk` | GET | `RiskState` | refresh ogni 10s |
| `/api/paper/feed?limit=50` | GET | `FeedEvent[]` | poll 3s, future: WebSocket |
| `/api/paper/signals/last` | GET | `Record<Epic, AssetSignal>` | refresh 5s |
| `/api/paper/stop` | POST | `{ ok }` | conferma con MDL-01 |
| `/api/paper/emergency` | POST | `{ ok, closed: number }` | conferma con MDL-01 |

**Strategia di polling:** un solo `paper-trading.facade.ts` che orchestra i `signal()` Angular esposti al component. Niente polling separato in ogni component.

### 6.2 Tipi TypeScript da pubblicare (in `core/models/paper-trading.ts`)

Vedi spec dettagliata nella §3 — aggiungili al model file.

---

## 7 · Routing & navigation

`paper-trading.routes.ts` resta invariato — sostituisci solo l'implementazione del component caricato.

Aggiungi `data: { screenLabel: '02 Paper Trading' }` per la coerenza con i nostri label di audit (corrisponde alla regola di tagging `data-screen-label` su DOM root, vedi §3.6 della Bible).

---

## 8 · Test

### 8.1 Unit
- `position-card.component.spec.ts` — render con tutti i 7 campi, P&L positivo/negativo color check, trailing on/off
- `kpi-strip-compact.component.spec.ts` — sparkline render con/senza dati
- `risk-gauge-stack.component.spec.ts` — status mapping → color
- `live-feed-timeline.component.spec.ts` — kind → icon/color, max-rows clipping
- `cockpit-header.component.spec.ts` — emit stop/emergency

### 8.2 E2E (cypress, se presente)
- Apri pagina → verifica RUNNING pill rendered
- Click STOP → MDL-01 confermato → POST `/api/paper/stop` chiamato
- Click EMERGENCY → MDL-01 confermato → POST `/api/paper/emergency`
- Apri drawer da position card → drawer 380px visibile

---

## 9 · Definition of Done

- [ ] Sostituisce 1:1 `paper-trading.component.*` esistente, no rotture di route
- [ ] Tutti i componenti standalone, OnPush, signals
- [ ] Zero hex hardcoded — solo `p.$mantis-*`
- [ ] Zero `font-family: Arial / sans-serif / system-ui` nel SCSS
- [ ] Tutti i numeri in `var(--mantis-font-mono)` con `font-feature-settings: 'tnum' 1`
- [ ] HDR-01 implementato come Cockpit Header, riusato anche da Dashboard v2 se applicabile
- [ ] Position card con **tutti e 7** i campi richiesti
- [ ] Drawer dettaglio creato (anche se body placeholder), aperto da position card
- [ ] Empty state per "0 posizioni" implementato (no testo nudo)
- [ ] Loading: skeleton per position-card e live-feed (no spinner generico al centro)
- [ ] STOP / EMERGENCY confermati con MDL-01
- [ ] Polling unificato in un facade, non ripetuto per component
- [ ] Test unit per i componenti core (position-card, kpi-strip, cockpit-header)
- [ ] Page passa l'audit Style Bible §3 senza VIO-01..12

---

## 10 · PR plan suggerito

Per evitare un mega-PR:

1. **PR 1 — chrome:** `cockpit-header` (estratto in shared) + nuovo layout 3 colonne vuoto + tipi TS
2. **PR 2 — left rail:** `bot-vitals-panel` + `risk-gauge-stack` + `models-health-panel`
3. **PR 3 — center hero:** `kpi-strip-compact` + `position-card` + `active-positions-cockpit` + empty state
4. **PR 4 — telemetria:** `signals-heatmap` + `live-feed-timeline` + facade polling
5. **PR 5 — drawer + finiture:** `position-detail-drawer` (anche placeholder) + skeleton loading + audit pass

---

## 11 · Cosa NON fare

- ❌ NON portare avanti la Variant A (archiviata, non commit)
- ❌ NON usare CoreUI default `<button cButton color="primary">` — sostituiscilo con i nostri stili (BTN-01..05)
- ❌ NON fare un'unica tabella sotto un KPI flat (è il pattern attuale che stiamo sostituendo)
- ❌ NON aggiungere zebra striping a tabelle (VIO-05)
- ❌ NON inventare colori — se ti sembra di averne bisogno, manca un token: chiedi prima di aggiungerne uno
- ❌ NON usare radius 12/16/20 (VIO-01)
- ❌ NON committare i file `.jsx` in `mocks/`, sono solo referenza locale dello sviluppatore

---

## 12 · Appendix — Mock data per stub backend

Usa i dataset in `mocks/Shared.jsx` (PAPER_STATE, RISK_STATE, ASSET_UNIVERSE, LAST_SIGNALS) come **fixture di test** finché il backend non espone endpoint reali. Sono già rappresentativi del comportamento osservato.

---

*Handoff v1.0 · MANTIS AI · 27/04/2026 · target: GitBakko/AlgoTrader@main*
