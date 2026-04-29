# Paper Trading v2 — Style Bible §3 Audit (VIO-01..12)

**Data:** 2026-04-29
**Scope:** `frontend/src/app/views/paper-trading/` — view shell + 9 sub-components + drawer
**Bible reference:** `STYLE_BIBLE.md` v1.0 §3 Audit Rules — Top 12 Violazioni
**Build verifica:** `npx ng build --configuration=development` — clean (8.34 s)

---

## Risultato finale

**16 violazioni risolte** su 2 categorie:

- VIO-08 (heading uppercase con letter-spacing < .14em): **13 fix**
- VIO-07 (padding card > 20 px): **3 fix** (empty state)

Tutte le altre violazioni della Top 12: **0 occorrenze**.

| ID | Esito | Note |
|---|---|---|
| VIO-01 (radius 8/12/16/20) | ✅ pass | grep `border-radius:\s*(8\|12\|16\|20)px` → 0 hit |
| VIO-02 (numeri non tabulari) | ✅ pass | `.mantis-mono` global applica `font-feature-settings: 'tnum' 1, 'zero' 1` |
| VIO-03 (stato come testo nudo) | ✅ pass | tutte le pill via `pv-rg__pill` / `pv-pc__chip--dir` / `pv-feed__chip` / `pv-mh__badge` |
| VIO-04 (button CoreUI default) | ✅ pass | cockpit-header buttons custom; nessun `<button cButton color="primary">` nel view |
| VIO-05 (table senza sticky / zebra) | N/A | view senza tabelle |
| VIO-06 (P&L color non semantico) | ✅ pass | tutti i colori via token `var(--mantis-*)` o `p.$mantis-*` (zero hex literali) |
| **VIO-07 (padding card > 20 px)** | 🛠 fixed (3) | empty state — vedi diff sotto |
| **VIO-08 (uppercase senza letter-spacing .14-.22em)** | 🛠 fixed (13) | vedi diff sotto |
| VIO-09 (empty state nudo) | ✅ pass | active-positions, live-feed, drawer history hanno icona + title + sub |
| VIO-10 (spinner generico) | ✅ pass | skeleton-kpi-cell, skeleton-position-card + skeleton inline su feed/heatmap |
| VIO-11 (form senza label uppercase) | N/A | view senza form |
| VIO-12 (header coerente) | ✅ pass | `app-cockpit-header` (HDR-01) |

### Altri controlli passati

- 0 hex hardcoded (`#[0-9a-fA-F]{3,8}` su `paper-trading/**/*.scss` → no match)
- 0 `console.log`
- 1 `!important` legittimo: `bot-vitals-panel.scss:262` dentro `@media (prefers-reduced-motion: reduce)` per disabilitare animazioni — accessibilità, conforme

---

## Diff before/after

### VIO-08 — letter-spacing uppercase ≥ .14em

> Bible §0.1: "Section label IBM Plex · 10px · 700 · letter-spacing **.22em** UPPER" / "Micro label IBM Plex · 9px · 700 · letter-spacing **.14em** UPPER".

#### `signals-heatmap.component.scss`

**.pv-heatmap__epic / .pv-heatmap__dir** (line 62)
```diff
- letter-spacing: .1em;
+ letter-spacing: .14em;
  text-transform: uppercase;
```

**.pv-heatmap__state** (line 246)
```diff
- letter-spacing: .08em;
+ letter-spacing: .14em;
  text-transform: uppercase;
```

#### `bot-vitals-panel.component.scss`

**.pv-bv__pill** (line 121)
```diff
- letter-spacing: .12em;
+ letter-spacing: .14em;
  text-transform: uppercase;
```

#### `position-card.component.scss`

**.pv-pc__age-label** (line 92)
```diff
- letter-spacing: .12em;
+ letter-spacing: .14em;
```

**.pv-pc__chip** (line 114)
```diff
- letter-spacing: .12em;
+ letter-spacing: .14em;
```

**.pv-pc__triplet-label** (line 221)
```diff
- letter-spacing: .12em;
+ letter-spacing: .14em;
```

**.pv-pc__spark-empty** (line 369)
```diff
- letter-spacing: .12em;
+ letter-spacing: .14em;
```

**.pv-pc__meta-label** (line 394)
```diff
- letter-spacing: .08em;
+ letter-spacing: .14em;
```

**.pv-pc__close** (line 425)
```diff
- letter-spacing: .08em;
+ letter-spacing: .14em;
```

#### `position-detail-drawer.component.scss`

**.pdd-header__deal** (line 76)
```diff
- letter-spacing: .12em;
+ letter-spacing: .14em;
```

**.pdd-btn** (line 289)
```diff
- letter-spacing: .1em;
+ letter-spacing: .14em;
```

**.pdd-defs dt** (line 320)
```diff
- letter-spacing: .12em;
+ letter-spacing: .14em;
```

#### `live-feed-timeline.component.scss`

**.pv-feed__chip** (line 62)
```diff
- letter-spacing: .1em;
+ letter-spacing: .14em;
```

---

### VIO-07 — empty state padding ≤ 20 px

> Bible §3 VIO-07: "Padding card > 20px (troppo aerato)". Empty state dentro card → applica.

#### `active-positions-cockpit.component.scss` (.pv-apc__empty, line 109)
```diff
- padding: 32px 16px;
+ padding: 20px 16px;
```

#### `live-feed-timeline.component.scss` (.pv-feed__empty, line 308)
```diff
- padding: 32px 18px;
+ padding: 20px 16px;
```

#### `position-detail-drawer.component.scss` (.pdd-empty, line 338)
```diff
- padding: 24px 12px;
+ padding: 20px 12px;
```

---

## File modificati (7)

```
frontend/src/app/views/paper-trading/components/signals-heatmap/signals-heatmap.component.scss
frontend/src/app/views/paper-trading/components/bot-vitals-panel/bot-vitals-panel.component.scss
frontend/src/app/views/paper-trading/components/position-card/position-card.component.scss
frontend/src/app/views/paper-trading/components/position-detail-drawer/position-detail-drawer.component.scss
frontend/src/app/views/paper-trading/components/live-feed-timeline/live-feed-timeline.component.scss
frontend/src/app/views/paper-trading/components/active-positions-cockpit/active-positions-cockpit.component.scss
```

---

## Validazione runtime (Track C — NEXT_SESSION_PROMPT.md §C)

| # | Check | Esito |
|---|---|---|
| 1 | `GET /api/trading/pnl-history?minutes=10` → `data.points.length` | ✅ 10 punti, `source="snapshot"` |
| 2 | `position_pnl_snapshots` distinct prices ultimi 10 min | ⚠ NVDA: 1 distinct su 10 row — atteso, US stock chiuso pre-market 03:46 ET |
| 3 | `npx ng build --configuration=development` | ✅ clean 8.34 s, 0 errori |

---

## Track D — Prometheus snapshot counter (già attivo)

`backend/src/monitoring/metrics.py:163-167` registra:

```python
paper_pnl_snapshot_counter = Counter(
    "mantis_paper_pnl_snapshot_total",
    "Paper trading 60s P&L snapshot ticks recorded by outcome",
    ["outcome"],  # success | empty | error
)
```

`backend/src/data/pnl_snapshot_scheduler.py:162-166` chiama `MetricsCollector.record_paper_pnl_snapshot(outcome=...)` per ogni tick. Soddisfa l'obiettivo "see the 60s tick alive without DB peeking" via:

```promql
rate(mantis_paper_pnl_snapshot_total{outcome="success"}[5m]) > 0
```

Nessuna modifica necessaria.

---

*Generated 2026-04-29 — caveman session, applied directly on `main` per user direction.*
