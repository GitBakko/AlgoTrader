# Dashboard v2 — Fidelity Audit (mock JSX ↔ implementazione)

**Audit date**: 2026-04-24
**Fonte di verità**: `design_handoff_dashboard_v2/mocks/VariantB_Ambitious.jsx` + `OperationalStrip.jsx` + `TradeBreakdown.jsx` (`TradeBreakdownB` export) + `Shared.jsx`
**Oggetto analizzato**: `frontend/src/app/views/dashboard/dashboard-v2/` @ main `ae11edb`

**Metodologia**: ispezione JSX mock source linea-per-linea contro HTML/SCSS/TS componenti Angular.
Dimensioni coperte: A layout, B elementi visuali, C contenuti/metriche, D copy/labels, F interazioni/animazioni, G background/bordi/glow. Lasciata fuori **E typography** per fase 2 (cosmetica).

**Legenda severità**:
- 🔴 **Critical** — struttura/layout intero diverso. Utente vede dashboard "altra"
- 🟠 **Major** — componente esiste ma shape/contenuti sbagliati
- 🟡 **Minor** — dettaglio mancante, cosmetic-plus

**Legenda dati**:
- ✅ disponibile oggi
- ⚠ parziale / derivabile client-side
- 🔴 nuovo endpoint backend necessario

**Scala effort**: ore dirette.

---

## Sommario

Ho deviato **significativamente** dal mock in 2 zone:
1. **OperationalStrip** — ho costruito 6-tile status bar (basandomi sul testo README §7 preso letteralmente), il mock è 3-zone con Live P&L hero + 4 position cards + system stats 2x3 (che *sommano a 6 tile*, come mi hai fatto notare).
2. **Cockpit spine** — ho costruito 2-col (chart + KPI rail 8 righe), il mock è 3-col (left rail 3 KPIs / spine chart con peak+MaxDD markers / right rail 3 KPIs).

Anche top header e duration scatter hanno divergenze importanti. Bottom row restante (heatmap, TradeBreakdown) è più vicino al mock ma con dettagli da ripassare. OvernightSwap è per design diverso (scelta D1:B) ma senza la ring-viz del mock.

**Effort totale stimato**: ~26–32h di lavoro per allineamento completo.

---

## 1. Top-of-page (prima di OperationalStrip)

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 1.1 | **Mock NON ha "Top command bar"** con tabs+clock+KILL SWITCH. Ha header `Performance Cockpit` (h2 14px weight 600) + subtitle `since 2026-01-22 · 412 closed trades · regime-gated` (10px mono opacity 0.4) + segment tabs `[1D 7D 30D 90D YTD ALL]` a destra. Nessun KILL SWITCH, nessun clock live, nessun wordmark decorativo. | 🔴 Critical | 2h | Subtitle: `since` = prima `opened_at` ✅, `N closed trades` = `total closed` ✅, "regime-gated" = label statico ✅ |
| 1.2 | `Custom` come 7° opzione tab: mock NON ha Custom. Io l'ho aggiunto con date-picker. | 🟡 Minor | 0.25h (rimuovere) | N/A |
| 1.3 | Wordmark `MANTIS · DASHBOARD` centrato — non nel mock. | 🟡 Minor | 0.1h (rimuovere) | N/A |
| 1.4 | Live clock CET — non nel mock. | 🟡 Minor | 0.1h (rimuovere) | N/A |
| 1.5 | KILL SWITCH rosso con pulse — non nel mock VariantB ma README §5.2 lo richiede esplicitamente. **Aperta: tenere o rimuovere?** Proposta: spostare in pagina /paper-trading esistente (dove c'è già Stop). | 🟠 Major (decisione UX) | 0.5h rimozione, 1h spostamento | N/A |
| 1.6 | `gap: 10px` tra righe dashboard (mock) vs `gap: var(--mantis-space-2)` = 8px mio. | 🟡 Minor | 0.1h | N/A |

**Subtotale effort zona 1**: 3–4h

---

## 2. OperationalStrip — **riscrittura sostanziale**

Mock: grid `minmax(260px, 320px) minmax(0,1fr) auto`, 3 zone, padding `10px 14px`, gradient bg `linear-gradient(180deg, rgba(22,27,34,0.9) 0%, rgba(13,17,23,0.6) 100%)`, border accent 0.18.

Mia impl: `repeat(6, 1fr)` 6 tile indipendenti.

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 2.1 | **Struttura intera sbagliata**: 3 zone vs 6 tile. Richiede rewrite componente. | 🔴 Critical | 4h (base) | vedi sotto |
| 2.2 | **Zone 1 — Live P&L hero**: label `SESSION · Live P&L` (neon green 0.6 opacity) + dot pulse + `LIVE · US OPEN` label destra; hero number 28px mono weight 700 con glow text-shadow; delta pct 12px; bottom row mono 10px `Equity €X | Trades N | Peak +€X`. | 🔴 Critical | 2h | `daily_pnl` ✅ `equity` ✅ `trades today` ✅ (§2.5) · **Peak intraday** ⚠ (da computare client da paperPositions/closedPositions del giorno, oppure backend) · Session label "US OPEN" ⚠ (heuristica client UTC hour ok) |
| 2.3 | **Zone 2 — Open Positions**: label `Open Positions · N/8` + destra `Kelly ½ · K slots free`; grid 4-col di mini-card per ogni posizione live con: left-border 3px colored per P&L sign, symbol (11px bold) + direction ▲/▼ colored, P&L € bold + pct% muted, entry/mark price (se serve). | 🔴 Critical | 3h | `paperPositions[]` ✅ (epic/direction/upl/level/size) · Kelly stats ✅ (`paperStatus.kelly_stats`) · mark price via `ws.prices[epic]` ✅ · max positions "8" = config ✅ |
| 2.4 | **Zone 3 — System 2x3 grid**: label `System` + grid 2x3 mono 10px con: `Breakers N/6 OK`, `WS Live`, `Broker Capital`, `Mode DEMO`, `Funding -0.04%/8h`, `Regime Trend↑`. Colore per status (green/warning). | 🟠 Major | 2h | Breakers ✅ · WS status ✅ · Broker name="Capital" statico ✅ · Mode=`paperStatus.execution_mode` ✅ · Funding `ws.latencyMs` non c'entra — qui serve overnight swap del BTC o del paper-portfolio ⚠ (serve endpoint) · Regime ⚠ (esiste `paperStatus.correlation_regime` o `regime_gate.regime`) |
| 2.5 | Pulse glow animation 2s su dot Live in zone1 — ok già presente globalmente, solo assicurarsi posizionamento. | 🟡 Minor | 0.1h | N/A |
| 2.6 | Gradient bg `linear-gradient(180deg, rgba(22,27,34,0.9) 0%, rgba(13,17,23,0.6) 100%)` — io uso surface-2 piatto. | 🟡 Minor | 0.2h | N/A |

**Subtotale effort zona 2**: ~11h
**Dati nuovi necessari**:
- **Peak intraday P&L** — serve query DB "max cumulative P&L oggi" OR derivazione client da trade events del giorno (~1h backend o ~0.5h client)
- **Correlation regime label compatto** (es: "Trend↑") — esiste `correlation_regime` ma va formattato

---

## 3. Cockpit spine — **struttura 3-col da implementare**

Mock: outer card con `linear-gradient(180deg, #0d1117, #10161e)` + radial-gradient overlay `radial-gradient(circle at 50% 40%, rgba(57,255,20,0.04), transparent 60%)`, border accent 0.22, radius 8, padding 14 16. Inner grid `auto 1fr auto` (left rail 165px min / spine chart / right rail 175px min).

Mia impl: 2 colonne `2fr 1fr`, chart tv-lightweight + rail 8 righe.

### 3.1 Outer card e header

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 3.1.1 | Gradient bg + radial overlay neon su cockpit — assente nel mio SCSS. | 🟡 Minor | 0.3h | N/A |
| 3.1.2 | Header-bar sopra la spine card: `Performance Cockpit` title + `since 2026-01-22 · N closed trades · regime-gated` subtitle + segment tabs destra. **Nel mio impl è in `dv2-bar` component bar fuori dalla spine card**. | 🟠 Major | 1h | `since date` ✅ (min opened_at da DB) · `closed trades count` ✅ · "regime-gated" statico ok |
| 3.1.3 | Chart inline header: label `EQUITY SPINE` + legenda `▬ equity ┄ peak ▬ drawdown` + right `curr €X · ROI +X% · ann. +X%` (3 metriche). **Ho solo 1 metrica (equity) + delta pct.** | 🟠 Major | 1h | `curr equity` ✅ · **ROI %** ⚠ (derivabile: `(current_equity - initial_capital) / initial_capital`) · **ann. %** ⚠ (usare `calmar_ratio × max_drawdown` OR `(1 + total_return) ^ (252/days) - 1`, backend lo calcola già in `calmar_ratio` loop) |

### 3.2 Left rail (3 KPIs) — **nuovo componente**

Mock 3 righe:
- `Profit Factor` 1.87 neon + sub `gross +€24.8k / −€13.3k · soglia 1.3 ✓`
- `Calmar` 2.41 neon + sub `Sharpe 1.62 · Sortino 2.18`
- `Expectancy` +€27.60 bianco + sub `per trade · N closed`

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 3.2.1 | Left rail con 3 KPI (accent border-left 2px) — **oggi assente**. | 🔴 Critical | 2h | `profit_factor` ✅ · gross profit/loss ✅ (derivabile da `avg_win × win_count` e `avg_loss × loss_count`) · `calmar_ratio` ✅ · `sharpe_ratio` ✅ · `sortino_ratio` ✅ · **Expectancy** ⚠ (derivabile: `win_rate × avg_win + (1-win_rate) × avg_loss`) |

### 3.3 Spine chart — **SVG custom vs lightweight-charts**

Mock: SVG 900x190 viewBox custom con:
- Grid pattern 45x20
- Breakeven dashed horizontal at y=55%
- Equity area gradient neon con drop-shadow filter
- Peak line dashed bianca 25%
- Drawdown area rossa gradient sotto breakeven
- Drawdown line rossa
- **Peak marker**: circle fill neon con drop-shadow + label `PEAK €X.XXX`
- **Max DD marker**: circle fill red con drop-shadow + label `MAX DD X.X%`
- Breakeven text label bottom-left

Mia impl: `app-tv-chart` lightweight-charts area mode. Niente markers, niente drawdown area stilizzata sotto breakeven, niente peak line dashed.

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 3.3.1 | **Peak marker** con circle + label "PEAK €X" sul chart. Lightweight-charts supporta markers via `series.setMarkers()` — fattibile ma label positioning limitato. Alternativa: custom SVG sopra chart (più controllo). | 🟠 Major | 2h (markers API) / 4h (SVG overlay) | `equity_curve` ha tutti i punti ✅, peak = argmax(equity) |
| 3.3.2 | **Max DD marker** — idem 3.3.1. | 🟠 Major | 1h (incluso in 3.3.1) | `drawdown_pct` in equity_curve ✅, argmin |
| 3.3.3 | **Peak line dashed** (linea orizzontale di peak value proiettata) — overlay series aggiuntiva in lightweight-charts (una linea piatta al peak). | 🟡 Minor | 0.5h | `equity_curve` ✅ |
| 3.3.4 | **Drawdown area rossa sotto breakeven** — oggi il mio tv-chart ha `drawdownData` come overlay ma la rappresentazione non è area rossa gradient invertita. | 🟠 Major | 2h | `drawdown_pct` per day ✅ |
| 3.3.5 | Grid pattern background + breakeven dashed line — lightweight-charts grid già di default, breakeven custom come `PriceLine`. | 🟡 Minor | 0.5h | N/A |
| 3.3.6 | Date axis inline (Jan 22, Feb 14, ...) — lightweight-charts lo fa da sé, stile va adattato. | 🟡 Minor | 0.3h | N/A |

**Alternativa radicale**: sostituire completamente lightweight-charts con SVG custom (come mock). Effort: ~6h ma controllo totale. **Proposta**: tenere lightweight-charts e aggiungere markers+PriceLine (copertura 3.3.1-5 in ~4h).

### 3.4 Right rail (3 KPIs) — **nuovo componente**

Mock 3 righe con right-border 2px accent (mirrored):
- `Max Drawdown` −8.42% red + sub `12d dal peak · rec. in corso`
- `Current DD` −2.1% warning + sub `€54,812 vs peak €57,340`
- `Win Rate` 62.4% green + sub `258W · 154L · ▲ +1.8pp`

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 3.4.1 | Right rail 3 KPI (invece dei miei 8) — rewrite KpiRail O nuovo CockpitRightRail. | 🔴 Critical | 2h | `max_drawdown` ✅ · `current_drawdown_pct` ✅ · peak equity ✅ (DB o `risk_status`) · `win_rate` + `win_count` + `loss_count` ✅ · **"+1.8pp vs periodo precedente"** ⚠ (serve delta vs timeframe precedente — nuovo aggregato) · **"12d dal peak"** ⚠ (derivabile da equity_curve: days since argmax) · **"rec. in corso"** ⚠ (derivabile: `current < peak`) |

### 3.5 Perché eliminare le 8 righe rail mie?

Mock ha solo 6 KPI totali in 2 rail (3+3). Le mie 8 righe attuali (Daily P&L, Open positions, Unrealized P&L, Net exposure, Drawdown, Sharpe, Win rate, Hit rate TP) hanno **overlap** con OperationalStrip zone1 (Daily P&L / open positions / unrealized già lì).

**Proposta**: eliminare KpiRailComponent, creare `CockpitLeftRail` + `CockpitRightRail` con shape mock.

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 3.5.1 | KpiRail eliminata/sostituita | (incluso in 3.2.1 + 3.4.1) | 0 | N/A |

**Subtotale effort zona 3**: ~10–12h
**Dati nuovi necessari**:
- ROI % (derivabile client — 5min)
- Annualized return (backend lo calcola già in `annualized_return`, esporlo separatamente — 0.5h)
- Expectancy (derivabile client — 5min)
- Peak equity con timestamp (da equity_curve argmax — 5min client)
- Days since peak (idem)
- **Δ win_rate vs periodo precedente** 🔴 — serve nuovo endpoint O query a 2 periodi poi diff client (~1h)

---

## 4. Bottom row (duration · funding/swap · heatmap)

Mock: grid `1fr 1fr 1.7fr`, gap 10px.

### 4.1 Duration × PnL scatter

Mock: 180 punti random, card con:
- Label `Duration ✕ PnL` + right `180 trade · €/h axis`
- SVG 280x140 con grid pattern bg, median vertical lines dashed, y-axis labels `+€` top-left `−€` bottom-left `dur →` bottom-right
- Points: circle r=2.2, opacity 0.65, highlighted points con drop-shadow quando |pnl|>300
- Below: 2-col legend mono 10px `● win 47m · +€38.20/h` / `● loss 1h08m · −€28.70/h`
- Bias alert (condizionale): `⚠ loss dura 45% più del win · late-exit bias` su warning bg con border-left 2px

Mia impl:
- Label ok
- Meta "N trade · €/h axis" ✅
- SVG viewBox 100x100 (aspect ratio stretta)
- Grid pattern ❌ mancante
- Median lines orizzontali mi servono — io ho fatto verticali andando mid→top/bot, mock fa da x=xS(47) verso y=yS(200) cioè linee più eleganti
- Y-axis labels +€/-€/dur→ ❌ mancanti
- Legend mono 2-col ok con colored dot ma manca **`€/h` metric** che richiede calcolo `avg_pnl / avg_duration_hours` per win e per loss
- Bias alert ok ma testo ha "⚠ loss dura +{X}% del win · late-exit bias" vs mock "⚠ loss dura {X}% più del win · late-exit bias" — copy leggermente diverso

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 4.1.1 | **Grid pattern background** sullo scatter plot. | 🟡 Minor | 0.2h | N/A |
| 4.1.2 | **Y-axis labels** (`+€`, `−€`, `dur →`) nelle 3 corner. | 🟡 Minor | 0.3h | N/A |
| 4.1.3 | **Median vertical lines** dashed (win neon, loss red) — già presenti ma shape diversa (io da midline verso scatter extreme). Review. | 🟡 Minor | 0.3h | `duration_medians` ✅ (backend §2.6) |
| 4.1.4 | **`€/h` metric nel legend** (`+€38.20/h` / `−€28.70/h`). Calcolo: `avg_pnl_per_win / (avg_win_duration_min / 60)`. | 🟠 Major | 0.5h | ⚠ derivabile da `performance.avg_win`+`avg_loss` + `duration_medians.win_avg_min`+`loss_avg_min` ✅ |
| 4.1.5 | Copy bias alert: `"⚠ loss dura X% più del win"` invece di `"+X%"` | 🟡 Minor | 0.1h | N/A |
| 4.1.6 | Highlight drop-shadow sui punti estremi (|pnl|>300 o top 30%) | 🟡 Minor | 0.3h | `profit_loss` disponibile ✅ |
| 4.1.7 | Aspect ratio viewBox 280x140 (2:1) invece di 100x100 (1:1) | 🟡 Minor | 0.1h | N/A |

### 4.2 Funding Ring → Overnight Swap

**Design decision già presa**: D1:B sostituisce Bybit con Capital.com overnight swap. Tuttavia il mock ha una **ring viz** che ho perso completamente.

Mock: card con:
- Label `Funding Exposure` + right badge `BYBIT · BTC` (warning color)
- SVG 96x96 ring:
  - Base circle stroke `rgba(255,255,255,0.06)` stroke-width 8
  - Foreground circle stroke warning color, `strokeDasharray="239"` proporzionale a `|rate|/0.5%`, `strokeLinecap="round"`, rotate -90°, drop-shadow
  - Center text `-0.04%` (11px weight 700) + subtext `per 8h` (8px muted)
- Right of ring: stats column
  - `-€127.40` (20px red) 
  - `7d accum` label
  - `BTC long 0.12`
  - `€7,858 notional`
  - `next 04:38` (warning color)

Mia impl (OvernightSwap):
- Badge `BYBIT · BTC` → io ho `{{epic}}` dinamico ✅ — ma etichetta card `Overnight Swap` invece di `Funding Exposure`
- **Ring SVG**: ho un placeholder ring con strokeDasharray statica "1 238.76" — NON proporzionale al rate
- **Center text ring**: io ho `—`, mock ha rate percentuale
- **Right column stats**: io ho 3 rows strutturate (long rate / short rate / footer) — mock ha 5 linee free-flow
- **Notional/7d accum/next charge countdown**: manca notional (richiede posizione aperta × prezzo), manca 7d accum (serve historical swap), countdown charge ✅ presente

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 4.2.1 | **Ring viz proporzionale al rate**: dasharray computato da `|long_rate_pct|` normalizzato a range. | 🟠 Major | 1h | `long_rate_pct` ✅ (static fallback o broker) |
| 4.2.2 | **Center text ring** = rate %. | 🟡 Minor | 0.2h | idem ✅ |
| 4.2.3 | **Notional € stimato** = `size × level × price` per BTC long (se esiste in paper positions). | 🟠 Major | 0.5h | ⚠ derivabile da `paperPositions[epic==BTCUSD]` se presente, altrimenti N/A |
| 4.2.4 | **7d accumulated €** — richiede tracciare swap storici. | 🔴 Critical | 3h | 🔴 **NEW**: serve nuovo endpoint o computato in BE come `rate × notional × 7`; alternativa: stima semplice `rate × notional × 7` client-side |
| 4.2.5 | **"BTC long 0.12" row** — info direzione+size posizione specifica. | 🟡 Minor | 0.3h | ✅ da paperPositions |
| 4.2.6 | Footer `next 04:38` countdown — ho già l'implementazione ✅ |  ✅  | 0 | ✅ |
| 4.2.7 | Label `Funding Exposure` vs `Overnight Swap` — **domanda design**: usare nome originale del mock per consistenza visiva, o mantenere il nome tecnico nostro? | 🟡 Minor (decisione) | 0.1h | N/A |

**Subtotale effort 4.2**: ~5h (se si implementa 7d accum) o ~2h (senza 7d)

### 4.3 Calendar heatmap 90d

Mock:
- Label `Daily Heatmap · 90d` + right `best +€1,408 · worst −€612`
- Grid con colonna day-of-week (M T W T F S S, 8px muted, width 14, height 26)
- Weeks arranged horizontally, ogni week = colonna con 7 cells (26px tall ciascuna, 3px gap)
- **Cells con P&L text dentro**: se trades > 0, mostra `+1.4k` o `−612` formattato (8px mono bold)
- Cell color: green ramp 0→neon / red ramp 0→#FF3D57, alpha based on `|pnl|/max`
- Focused cell scale 1.15 + `border: 1px solid #fff` + `outline: 1px solid rgba(255,255,255,0.4)`
- Glow box-shadow su cells top (n>0.7 intensity)
- Focus card right: 170px min-width con:
  - Label `Focus` (9px 0.2em)
  - Date weekday short (11px, 0.85 opacity)
  - P&L (20px weight 700, colored con text-shadow, "— flat" se zero)
  - Trade count + wins/losses (`N trade · WW NL`)
  - **`X% equity · Y% hit`** extra row con equity share e win rate della giornata

Mia impl:
- Label ok ✅
- Best/worst ok ✅
- Day-of-week col ok ✅
- Cells 14px height (mock 26px) — **troppo piccole, difficile leggere**
- **No testo P&L dentro le cells** — principale gap visivo
- Color intensity ok ✅
- Focus scale 1.15 + border bianco ok ✅
- Focus card right ok ma manca `X% equity · Y% hit` extra row

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 4.3.1 | **Cells 14px → 26px** per leggibilità P&L inline | 🟠 Major | 0.2h | N/A |
| 4.3.2 | **P&L text dentro cells** (`+1.4k` / `−612`) quando `trades > 0` | 🟠 Major | 0.5h | `daily_pnl` ✅ |
| 4.3.3 | **Glow box-shadow su cells top-intensity** (>70%) | 🟡 Minor | 0.2h | N/A |
| 4.3.4 | **Focus card: `X% equity · Y% hit` row** — `pnl/equity*100` + `wins/trades*100` | 🟡 Minor | 0.3h | ✅ (serve equity giornaliero) |
| 4.3.5 | "— flat" vs `— no trades` per giorni zero — copy check | 🟡 Minor | 0.1h | N/A |

**Subtotale effort 4.3**: ~1.5h

**Subtotale effort zona 4**: ~9–11h

---

## 5. TradeBreakdown (Deliverable C)

Mock: `TradeBreakdownB` (non A). Card stesso layout del mio. Differenze minori:

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 5.1 | Header right meta ha **`Σ N trade`** totale (io mostro solo days count + legend) | 🟡 Minor | 0.2h | ✅ (somma su breakdown) |
| 5.2 | Zero-axis label `0` top-right del rigo orizzontale — **mancante** (mock ha span absolute) | 🟡 Minor | 0.1h | N/A |
| 5.3 | Hover highlight: mock colora background `rgba(255,255,255,0.04)` della colonna anche su cella vuota (weekend). Verificare che mio template faccia lo stesso su `d.empty`. | 🟡 Minor | 0.2h | N/A |
| 5.4 | Mock tracking: **default focus su last day** (i.e. today) — mio codice lo fa via `focusedIndex() ?? arr.length - 1` ✅ | ✅ | 0 | N/A |
| 5.5 | Focus card glow text-shadow su pnl positive ✅ già fatto | ✅ | 0 | N/A |
| 5.6 | Copy header: mock `Trade Breakdown · per day · BUY ▲ / SELL ▼` ✅ già fatto | ✅ | 0 | N/A |
| 5.7 | X-axis labels con `· today` suffix ✅ già fatto | ✅ | 0 | N/A |

**Subtotale effort zona 5**: ~0.5h

---

## 6. Global / container

| # | Gap | Severità | Effort | Data |
|---|-----|:--:|:--:|:--:|
| 6.1 | Background body `#0a0e13` (mio, da README §5.1) vs `#0d1117` mock. | 🟡 Minor | 0.05h (1 line change) | N/A |
| 6.2 | Animation `fade-slide-up 250ms` on mount — presente mia impl ✅ ok | ✅ | 0 | N/A |
| 6.3 | Reduced-motion handling — presente ✅ | ✅ | 0 | N/A |

**Subtotale effort zona 6**: ~0.1h

---

## 7. Discrepanze con audit precedente `2026-04-23_dashboard-v2-audit.md`

L'audit precedente (data-availability-focused) ha queste discrepanze con questo audit visual-focused:

| Area | Audit prec. | Fidelity audit |
|------|-------------|-----------------|
| KPI rail = 8 righe | documentato come design | **errato vs mock** (mock = 3+3 rail laterali) |
| OperationalStrip 6-tile | listato correttamente | interpretato male — mock è 3-zone (che contiene 6 tile) |
| Funding ring skeleton | previsto TODO | **ho perso la ring-viz stessa**, non solo i dati |
| Heatmap cells 14px | non discusso | troppo piccole vs mock 26px con testo dentro |
| Headline metrics spine "curr/ROI/ann" | non discusso | 3 metriche invece di 1 |
| Peak/MaxDD markers chart | non discusso | elementi visuali mancanti |
| Left rail (Profit Factor/Calmar/Expectancy) | non discusso | 3 KPI completamente mancanti |

**Conclusione**: audit precedente era fedele sul **piano dati**, inadeguato sul **piano visuale**. Questo audit copre il gap.

---

## 8. Riepilogo effort per zona

| Zona | Effort min-max |
|------|:-:|
| 1. Top header | 3–4h |
| 2. OperationalStrip | 11h |
| 3. Cockpit spine | 10–12h |
| 4. Bottom row | 9–11h |
| 5. TradeBreakdown | 0.5h |
| 6. Global | 0.1h |
| **Totale** | **~33–38h** (include decisioni design pending) |

Se si skippa il 7d funding accum (gap 4.2.4) e si tiene lightweight-charts base senza SVG custom (gap 3.3): **~26h**.

---

## 9. Dati che richiedono NEW backend

Solo **1** davvero nuovo:

1. **7d accumulated swap € per epic aperta** (gap 4.2.4) — richiede job che somma `rate × notional` over 7d. Alternativa: stima semplice `rate × notional × 7` client-side (effort: 0 backend, accuracy: bassa).

Tutti gli altri "nuovi dati" sono **derivabili client-side** da quanto già in DB:
- ROI, expectancy, peak equity/timestamp, days-since-peak, €/h metric, position P&L pct, win rate delta tra periodi (se si vuole davvero vs periodo precedente, quello richiede una 2nd query)

Se vuoi il **win_rate delta vs periodo precedente** (gap 3.4.1 sub), serve chiamare `/performance` con `days=30` e `days=60` e fare diff client, OPPURE nuovo endpoint `/performance/delta?tf=30D`. Effort backend: 1h.

---

## 10. Raccomandazione di phasing

### Phase 1 — Quick wins visuali (6h)
- 5 TradeBreakdown polish (0.5h)
- 6 global bg (0.05h)
- 4.3 heatmap cells 26px + P&L inline + glow + focus extra row (1.5h)
- 4.1 duration scatter grid pattern + y-axis labels + €/h legend + viewBox ratio (1.5h)
- 3.1.1 cockpit outer gradient + radial overlay (0.3h)
- 1.6 gap 10px + 1.2/1.3/1.4 rimozioni (0.5h)
- 3.1.3 chart inline header 3 metriche (1h)
- 4.2.1-4.2.3 overnight-swap ring viz + notional (1.5h)

### Phase 2 — Ristrutturazioni grosse (18h)
- 2 OperationalStrip riscrittura completa 3-zone (11h)
- 3.2 Left rail (Profit Factor/Calmar/Expectancy) (2h)
- 3.4 Right rail (Max DD/Current DD/Win Rate) (2h)
- 1.1 Top header `Performance Cockpit` + subtitle (2h)
- 1.5 decisione KILL SWITCH (0.5h)
- 3.5 cleanup KpiRail dismissione (0.5h)

### Phase 3 — Chart SVG markers (5–6h)
- 3.3 Peak marker + Max DD marker + peak line + drawdown area + breakeven (4–6h)

### Phase 4 — Opzionali
- 4.2.4 7d accumulated swap (3h se backend, 0h se stima)
- 3.4.1 win_rate delta (1h backend)

---

## 11. Decisioni aperte (serve tuo input)

1. **D-A — KILL SWITCH top bar**: mantenere (diverge da mock ma README §5.2 lo chiede), spostare in /paper-trading, o rimuovere?
2. **D-B — Custom timeframe tab**: tenere (miglioramento nostro) o rimuovere per allineamento mock?
3. **D-C — Chart engine**: lightweight-charts + markers API (sconsigliato per peak/DD labels, limitato) o SVG custom (più controllo, +4h)?
4. **D-D — 7d accumulated swap**: stima client `rate×notional×7` (facile, impreciso) o backend storico vero (3h, preciso)?
5. **D-E — Nome card 4.2**: `Overnight Swap` (tecnico nostro) o `Funding Exposure` (mock)?
6. **D-F — win_rate delta vs periodo precedente** (sub 3.4.1): lo vogliamo davvero? Serve nuovo endpoint o 2a chiamata. Oppure sub più semplice (es: "258W · 154L").
