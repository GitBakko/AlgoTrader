# MANTIS AI — Style Bible v1.0

**Versione:** 1.0 · 27/04/2026
**Stato:** vincolante — qualsiasi pagina che viola queste regole va rifatta.
**Sorgente:** estratto da `dashboard_v2` + `paper_trading_v2` (la nuova base visiva del prodotto).

> Riferimento normativo per ogni schermata di MANTIS AI. Quando ridisegni una pagina, parti dalla composizione delle primitive qui sotto — non reinventare button, table, chip ogni volta.

---

## 0 · Foundations

### 0.1 Design Tokens

Una sola fonte di verità: **`frontend/src/scss/_palette.scss`** (+ tokens Sass derivati).
- **Mai** colori hardcoded nei component template/style.
- **Mai** font diversi da quelli definiti.
- I tokens vengono esposti anche come CSS custom properties (`--mantis-*`) in `_custom.scss`.

#### Color Tokens

| Token | Hex | Use |
|---|---|---|
| `--mantis-neon` | `#39FF14` | Hero accent (solo dark): logo, focus, RUNNING, profit hero |
| `--mantis-green` | `#00d97e` | Primary brand (testo accent, link, border accent) |
| `--mantis-cyan` | `#00E5FF` | Secondary accent: TRAIL ON, info, ATTIVO, stati intermedi |
| `--mantis-loss` | `#FF3D57` | Loss, ERROR, REJECTED, SL, EMERGENCY |
| `--mantis-warning` | `#FFB020` | WARN, DEMO, near-threshold, STOP soft |
| `--mantis-neutral` | `#8B949E` | HOLD, IDLE, disabled, hint |
| `--mantis-surface-1` | `#0d1117` | Body bg |
| `--mantis-surface-2` | `#161b22` | Cards, sidebar |
| `--mantis-surface-3` | `#1c2128` | Dropdown, popover, tooltip-bg |

Border accent default: `1px solid rgba(0,217,126,.15)` (green tenue).
Background hover row tabella: `rgba(57,255,20,.03)`.

#### Typography

| Token | Family · Size · Weight | Use |
|---|---|---|
| UI sans | **Plus Jakarta Sans** | Tutto il chrome UI: titoli, paragrafi, label button normali |
| Mono | **IBM Plex Mono** | Numeri, ticker, codici, label uppercase, KPI, prezzi |
| H1 (page title) | Plus Jakarta · 24-32px · 700 | Solo nei page-header principali |
| H2 (section) | Plus Jakarta · 18-20px · 600 | Sotto-sezioni dentro pagina |
| Section label | IBM Plex · 10px · 700 · letter-spacing .22em UPPER | Etichette di blocco ("STATO", "RISK MANAGEMENT") |
| Body | Plus Jakarta · 13-14px · 400 | Testo descrittivo |
| Tabular | IBM Plex · `font-feature-settings:'tnum' 1` | **Qualsiasi** numero in colonna o KPI |
| Micro label | IBM Plex · 9px · 700 · letter-spacing .14em UPPER · `#ffffff66` | Sopra valori KPI, dentro le card |

Regola d'oro: **se è un numero, è IBM Plex Mono con `tnum` attivo.** Sempre.

#### Spacing & Radii

| Token | Value | Use |
|---|---|---|
| `--mantis-space-2` | 8px | Gap tra chip, padding compatto |
| `--mantis-space-3` | 12px | Gap interno card |
| `--mantis-space-4` | 16px | Padding card default |
| `--mantis-space-6` | 24px | Gap tra sezioni di pagina |
| `--mantis-radius-sm` | 4px | Button, chip, input, badge |
| `--mantis-radius-md` | 6-8px | Card, modal, panel |
| `--mantis-radius-pill` | 100px | Status pill, scroll thumb |

> **Mai** radius 12-16-20: rompe il linguaggio (industriale, non amichevole).

---

## 1 · Components

### 1.1 Card / Panel

Il primitivo di contenimento più frequente. Tre livelli: **standard**, **accent** (border-top colorato), **hero** (glow interno). Mai gradient pesanti, mai shadow esagerate.

#### CARD-01 · Surface · Border · Radius
- Background `#161b22` (surface-2)
- Border `1px solid rgba(0,217,126,.15)`
- Radius `6px`
- Padding interno `12-14px`

**DON'T:** light bg, border generico grigio, radius 16+, shadow drammatica, font di sistema.

#### CARD-02 · Accent border-top per categorizzare
Le card KPI usano `border-top: 2px solid <categoryColor>`. Il colore comunica la natura del dato:
- **green** (`#00d97e`) = profit / iterazioni / OK
- **cyan** (`#00E5FF`) = info / segnali / attivo
- **red** (`#FF3D57`) = loss / errori
- **neon** (`#39FF14`) = stato hero / running

#### CARD-03 · Status border-left per liste
Le card in lista (position card, alert, log row) usano `border-left: 3px solid <stateColor>`. Sostituisce le icone di stato a sinistra, è più scannabile in una list lunga.

```
border-left: 3px solid #FF3D57;  /* loss */
border-left: 3px solid #39FF14;  /* profit */
border-left: 3px solid #00E5FF;  /* trail-on / pending */
```

---

### 1.2 Page Header

Ogni pagina parte con un header coerente. Tre formati:

#### HDR-01 · Cockpit Header (live data + actions)
**Per Dashboard e Paper Trading.** Pagine "live" con stato + azioni critiche.
- Logo Mantis (signet 22px) + label `MANTIS AI ·` mono uppercase
- Page title (14px, 700)
- Status pill RUNNING (verde con dot pulsante) + DEMO (warn ghost)
- Spacer flessibile
- Button STOP (warning) + EMERGENCY (danger) right-aligned
- Background con leggero gradient verde dall'alto: `linear-gradient(180deg, rgba(57,255,20,.04) 0%, transparent 100%)`
- Border-bottom `1px solid rgba(57,255,20,.18)`

#### HDR-02 · Standard Header (page title + meta + filters)
**Per Posizioni, Segnali, Trade Journal, Backtest** — pagine list/data.
- Eyebrow mono `Trading · Cronologia` in green/70 uppercase
- Title 20px 700
- Meta (es. `142 chiuse · 2 aperte`) mono 10px white/50
- Spacer
- Button ghost (Export CSV) + secondary (New Filter)

#### HDR-03 · Settings Header (sub-nav)
**Per Settings, Strategia, Modelli AI** — pagine config con sub-tab.
- Block title come HDR-02
- Sub-nav underline subito sotto (vedi TAB-01)

> **Mai** un titolo di pagina nudo dentro al body — sempre dentro un'header strip.

---

### 1.3 Tables

Le tabelle sono ovunque (Posizioni, Segnali, Trade Journal). Devono essere **dense, leggibili, sticky-header, numeri tabulari**.

#### TBL-01 · Header style
- Mono uppercase, 9px, letter-spacing .16em
- Color `rgba(255,255,255,.5)`
- Padding `9px 12px`
- Border-bottom verde tenue `1px solid rgba(0,217,126,.15)`
- **Sempre sticky** quando la tabella supera 12 righe

#### TBL-02 · Densità · numeri tabulari · hover
- Default densità **cozy** (8-9px padding cella)
- Per list lunghe: **compact** (6px)
- Numeri sempre con `font-feature-settings:'tnum' 1`
- Hover row: `rgba(57,255,20,.03)` tint (verde appena percepibile)

#### TBL-03 · Numbers right-align, status pill, zebra OFF
- Tutti i valori numerici (P&L, prezzo, size, %) **right-aligned**
- Stato come pill, mai come testo nudo colorato
- **Mai zebra striping** — il border bottom riga è sufficiente, lo zebra rompe la pulizia su dark

---

### 1.4 Buttons

5 varianti, tutte mono uppercase. **Mai** usare CoreUI `btn-primary` generico — sostituiscilo con queste classi.

| Variant | BG | Border | Color | When |
|---|---|---|---|---|
| **Primary** | `#39FF14` | `#39FF14` | `#0d1117` | Una sola per pagina (Start, Save, Submit) |
| **Secondary** | cyan ghost (rgba 8%) | cyan/40 | `#00E5FF` | Azioni informative secondarie |
| **Ghost** | `rgba(255,255,255,.04)` | white/12 | white/85 | Cancel, Back, azioni neutre |
| **Warning** | warn ghost (rgba 8%) | warn/40 | `#FFB020` | Stop bot (reversibile) |
| **Danger** | `#FF3D57` | `#FF3D57` | `#fff` | Emergency, Delete (irreversibile) |

#### BTN-01 · Mai più di 1 primary per area visibile
Una sola primary action per "vista" alla volta. Tutto il resto è secondary/ghost. Se ci sono 3 primary nella stessa pagina, qualcosa non va nella gerarchia.

Stile button (tutti):
- Mono, 11px, 700, letter-spacing .08em uppercase
- Padding `6px 12px`
- Radius 4px
- Hover: brightness +8% / glow del color associato

---

### 1.5 Chip / Badge / Pill

Tre famiglie distinte. **Non confonderle.**

#### CHIP-01 · Status Pill (rounded full, con dot pulsante)
Per stato di un'entità live (bot, market, posizione).
- **Sempre rounded 100px**
- Dot pulsante a sinistra se "live"
- Mono 9px 700 letter-spacing .14em uppercase
- Padding `2px 8px`

Esempi: `RUNNING`, `DEMO`, `ERROR`, `ATTIVO`, `IDLE`.

#### CHIP-02 · Data chip (rounded 4, label + value)
Per metadata associato a una riga (uptime, age, distance, R:R).
- **Rounded 4px**
- Label uppercase mono 9px + value mono 11px bold
- Padding `3px 8px`
- Background tinted del color associato a 6-8% opacity

Esempi: `AGE 27m`, `TRAIL ON`, `R:R 1:1.94`.

#### CHIP-03 · Direction badge (BUY/SELL/HOLD)
- Mono 9px 700 letter-spacing .12em
- Padding `2px 7px`, radius 3px
- Background tinted (10% opacity), border tinted (20%)
- BUY=green, SELL=red, HOLD=neutral

> **Mai** "BUY" come testo nudo colorato in tabella — sempre badge.

---

### 1.6 Form / Input

#### FRM-01 · Input field
- Background `rgba(255,255,255,.025)`
- Border `rgba(255,255,255,.1)`, radius 3px
- Mono 11px
- Focus → border verde `#39FF14` + glow soft `0 0 0 3px rgba(57,255,20,.1)`
- **Mai** il blue browser default focus

Label sopra l'input: mono 9px 700 letter-spacing .14em uppercase white/55, gap 4px.

#### FRM-02 · Validation states
- **Errore:** border `#FF3D57` + box-shadow `0 0 0 3px rgba(255,61,87,.1)` + helper text mono 10px rosso sotto l'input con icona `⚠`
- **Warning:** ambra `#FFB020`
- **Helper text neutrale:** mono 10px white/40

---

### 1.7 Filter Bar

Pattern uniforme per ogni list page (Posizioni, Segnali, Trade Journal).

#### FLT-01 · Composizione
- Container: `#161b22`, border accent verde, padding 10×12, radius 6
- Label `FILTRI` mono 9px white/50 a sinistra
- **Date range sempre primo**, **search sempre ultimo (right-aligned, flex 1)**
- Filtri attivi: background verde 6%, border verde 25%, color verde, terminano con `×` per rimuoverli
- Reset button ghost a destra prima/dopo il search

---

### 1.8 Tabs

#### TAB-01 · Underline tab (full-width nav)
- Mono 10px 700 letter-spacing .14em uppercase
- Padding `10px 14px`
- Active: color `#39FF14` + border-bottom 2px verde
- Inactive: color white/50

#### TAB-02 · Segmented control (in-component switcher)
Per timeframe (1H/24H/7D/30D), view toggles, ecc.
- Container `#0d1117`, border white/8, radius 4, padding 2
- Item active: background verde 8%, color verde, radius 2
- Padding item `5px 12px`

---

### 1.9 Modal / Drawer

#### MDL-01 · Modal
**Per conferme + form brevi (max 2 step).**
- Backdrop semi-opaco `rgba(0,0,0,.7)`
- Card centrata, max-width **380-560px**
- Background `#161b22`, border verde 25%, radius 8, shadow `0 24px 48px rgba(0,0,0,.6)`
- Header: icona stato (28px circle tinted) + titolo 15px 700
- Body conciso, 12px white/65, line-height 1.5
- Footer: cancel ghost a sinistra, primary a destra, gap 8px

#### MDL-02 · Drawer (right-side)
**Per dettagli ricchi (history posizione, audit segnale).**
- Width **380px** default (440px se dense)
- Slide-in da destra, backdrop click-to-close
- Header sticky: titolo + close button (×) + eventuale tab strip
- Body scrollable
- Footer sticky con primary action right-aligned

---

### 1.10 Toast / Notification

In **alto-destra**. 4 tipi: success (verde), info (cyan), warning (ambra), error (rosso). Chiudibili con `×`. Auto-dismiss 5s.

- Background `#161b22`, border tinted 30%, **border-left 3px** del color tipo
- Radius 5px, padding `10px 12px`
- Icona stato a sinistra (✓/i/⚠/×), testo, close a destra
- Stack verticale gap 8px, max 4 visibili

---

### 1.11 Empty State

**Mai** solo testo nudo. Sempre:
- Icona/illustrazione 48-64px, opacity 0.4
- Titolo Plus Jakarta 16px 600
- Sottotitolo body 13px white/55
- CTA primary o secondary se applicabile

---

### 1.12 Loading / Skeleton

**Mai** spinner generico al centro pagina come unica indicazione.
- **Skeleton row/card** con shimmer per liste e card che sostituiscono il contenuto
- Skeleton: background `linear-gradient(90deg, #161b22 0%, #1c2128 50%, #161b22 100%)`, animazione 1.4s ease-in-out infinite
- Spinner ammesso solo dentro button durante submit (12px, color del button)

---

### 1.13 Pagination

- Mono 11px
- Container destra-allineato sotto la tabella
- `‹ 1 2 3 ... 12 ›` — page corrente background verde 8% color verde
- `Mostrando 1-25 di 142` mono 10px white/50 a sinistra

---

## 2 · Patterns

### 2.1 KPI Card Pattern

Composizione standardizzata per ogni KPI:
1. **Border-top** 2px del color categoria (CARD-02)
2. **Micro label** mono 9px white/55 uppercase (`P&L OPEN`, `WIN RATE`, ...)
3. **Valore primario** mono 22-26px 700 — color semantico (verde profit, rosso loss, white neutro)
4. **Sub-info** mono 10px white/40 — contesto/delta/timeframe (es. `vs ieri +€12`)
5. **Sparkline opzionale** in alto-destra absolute (28-40px alta, no axis, no label)

Padding card 12-14px.

### 2.2 Mini Charts (sparkline / bar)

- **No assi, no grid, no label**: sono pattern decorativi che amplificano il numero, non sostituiscono un chart vero
- Stroke 1.5px del color semantico
- Area fill stesso color a 12% opacity
- Width fluido, height 28-40px
- Per bar: gap 1px, radius 0, color semantico

### 2.3 Timeline / Live Feed

Per FeedSegnali, audit log, activity stream.
- Lista verticale, gap 6px tra row
- Ogni row: timestamp mono 10px white/40 a sinistra (fixed 60px) · dot color stato · contenuto a destra
- Riga "live" (più recente) ha dot pulsante e background hover-tinted

---

## 3 · Audit Rules — Top 12 Violazioni

Quando audito una pagina, parto da queste. Sono le rotture più frequenti dello stile.

| ID | Violazione |
|---|---|
| **VIO-01** | Card con radius 8/12/16 invece di 6 |
| **VIO-02** | Numeri non tabulari (font UI invece di mono) |
| **VIO-03** | Stato come testo nudo, non come pill |
| **VIO-04** | Button con stile CoreUI default (blu/grigio) |
| **VIO-05** | Tabella senza sticky header / con zebra striping |
| **VIO-06** | Colore P&L non semantico (`#0c0`/`#c00` invece dei token) |
| **VIO-07** | Padding card > 20px (troppo aerato) |
| **VIO-08** | Heading uppercase con letter-spacing default (deve essere .14-.22em) |
| **VIO-09** | Empty state con solo testo nudo, senza icona/CTA |
| **VIO-10** | Loading = spinner generico al centro pagina |
| **VIO-11** | Form senza label uppercase mono sopra l'input |
| **VIO-12** | Mancanza dell'header coerente (HDR-01/02/03) |

---

## 4 · Pagine MANTIS — Stato audit

Stato al **27/04/2026**. Ordine di refactor consigliato in fondo.

| # | Pagina | Pattern principali | Stato | Violazioni |
|---|---|---|---|---|
| 01 | **Dashboard** | HDR-01 · KPI Pattern · sparklines · heatmap | ✅ CONFORME | (revamp v2 done) |
| 02 | **Paper Trading** | HDR-01 · Position Card (CARD-03) · KPI strip · Risk Cockpit · Feed | ✅ CONFORME *(in handoff)* | (revamp v2 done — Variant B) |
| 03 | **Posizioni** | HDR-02 · Filter Bar · TBL-01/02/03 · Drawer dettaglio | 🟡 PARZIALE | VIO-02, VIO-03, VIO-05, VIO-12 |
| 04 | **Trade Journal** | HDR-02 · Filter Bar · TBL · Pagination · Empty State | 🔴 DA RIFARE | VIO-01, VIO-02, VIO-04, VIO-05, VIO-06, VIO-09 |
| 05 | **Segnali AI** | HDR-02 · Filter Bar · TBL + sparkline cell · Drawer | 🟡 PARZIALE | VIO-02, VIO-08 |
| 06 | **Backtest** | HDR-02 · Form lateral + KPI Pattern · sparklines | 🟡 PARZIALE | VIO-04, VIO-08, VIO-10 |
| 07 | **Strategia** | HDR-03 · Form sezionato · Validation states | 🔴 DA RIFARE | VIO-04, VIO-08, VIO-11, VIO-12 |
| 08 | **Modelli AI** | HDR-03 · Card grid · KPI Pattern · Tabs sub-nav | 🟡 PARZIALE | VIO-01, VIO-08 |
| 09 | **Risk Manager** | HDR-03 · Form + soglie · Validation states | 🟡 PARZIALE | VIO-04, VIO-11 |
| 10 | **Broker** | HDR-03 · Status pills · Form connection | 🟡 PARZIALE | VIO-03, VIO-04 |
| 11 | **Notifications** | HDR-03 · Form toggle · Toast preview | 🟡 PARZIALE | VIO-04, VIO-08 |
| 12 | **Settings** | HDR-03 · Form base · Tabs | 🔴 DA RIFARE | VIO-04, VIO-08, VIO-11, VIO-12 |
| 13 | **Login** | Card centered · Form base | ✅ CONFORME | — |
| 14 | **System Logs** | HDR-02 · Timeline / Live Feed · Filter Bar | ✅ CONFORME | — |

**Summary:** 4 conformi · 7 parziali · 3 da rifare.

**Ordine di refactor consigliato:**
1. **Settings** (#12) — pagina con più violazioni e impatto basso (rischio zero)
2. **Trade Journal** (#04) — alto traffico, stato attuale dissonante
3. **Strategia** (#07) — config critica, va resa robusta in input validation
4. Poi le PARZIALE in ordine di traffico stimato.

---

## Appendix A — Class & token convention

- **Tutte** le classi custom MANTIS sono prefissate `mantis-` quando aggiunte come override locali.
- I CSS custom properties: `--mantis-*` (vedi `_palette.scss`).
- Le classi di pattern documentate sopra (CARD-01, BTN-01, ecc.) sono **identificatori di regola**, non classi CSS — la classe CSS reale viene derivata dal componente Angular (`.position-card`, `.cockpit-header`, ecc.).

## Appendix B — Riferimenti repo

- `frontend/src/scss/_palette.scss` — color tokens
- `frontend/src/scss/_custom.scss` — chrome theme
- `frontend/src/app/views/dashboard-v2/` — referenza Dashboard (HDR-01, KPI pattern, sparklines)
- `frontend/src/app/views/paper-trading/` — **target di questo handoff** (Variant B)
- `frontend/src/app/views/design-system/` — pagina living style guide interna (mantenere allineata a questa Bible)

---

*Style Bible v1.0 · MANTIS AI · 27/04/2026*
