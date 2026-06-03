# Forward Demo Lab — Design Spec (v1, 2026-06-02)

**Status:** DESIGN — approved in brainstorming, not yet implemented. Terminal step = `writing-plans`.

> Premessa onesta: l'intera caccia all'alpha (mag–giu 2026) ha provato che MANTIS, post-fix
> del look-ahead leak (`63513aa`), **non ha edge direzionale**: il modello retrained leak-free
> va a caso, il sistema 4h MR idem. Quindi oggi MANTIS apre posizioni essenzialmente **a caso**,
> e — con spread + financing CFD — il baseline reale è **EV negativo** (bleed lento), non zero.
> Sperimentare è quindi *migliorativo per costruzione*, a patto che la sperimentazione produca
> **conoscenza statistica** e non sia una scommessa concentrata (n=1, zero potere).

## 1. Tesi del progetto

Demo Capital.com = ambiente di validazione **leak-immune e survivorship-immune per costruzione**:
il tempo va solo avanti (niente look-ahead) e si tradano solo strumenti esistenti ora (niente
survivorship). Tutti gli edge uccisi nella caccia sono morti di patologie da *backtest*
(leak, snooping, survivorship). Il forward demo le elimina alla radice.

Costruiamo un **lab di esperimenti forward**: N ipotesi spregiudicate ma **falsificabili**,
ciascuna con tesi d'entrata loggata, **sizing piccolo uniforme** (audacia sul *cosa*, disciplina
sul *quanto* — la concentrazione uccide il potere statistico, non protegge i soldi finti),
giudicate forward dallo stesso gauntlet statistico (`factory_stats`). Le vincenti graduano a
trial sample-grande / spread reale.

## 2. Hypothesis backlog (output del brainstorming "B")

Forward-native (il backtest coi nostri dati non le sa giudicare → demo informa davvero):

| ID | Ipotesi | Tesi | Cadenza | Tail-risk |
|---|---|---|---|---|
| **H2** | Gap-fade azioni US | Gap d'apertura senza catalyst riempiono parziale | 1 evento/giorno @ open | medio |
| H3 | Opening-Range Breakout (stocks-in-play) | Rottura range primi 5–15min + volume continua | intraday primi min | medio |
| H4 | Volatility-spike fade | Spike M5 > N×ATR senza news → overshoot reverte | monitor M1/M5 continuo | **ALTO (vende tail-risk)** |

Backtest-first (screen economico, **track parallelo** — vedi §9):

| ID | Ipotesi | Screen |
|---|---|---|
| H1 | Index RSI-2 dip-buy | backtestabile su OHLC daily; MR family, atteso decay post-2010 |
| H5 | Overnight drift (close→open) | uccidibile con 1 query: `mean(overnight_ret) > financing?` |

## 3. Decisioni bloccate (brainstorming)

1. **Execution model** = ordini VERI su **account demo dedicato**, isolato dal soak 18-asset.
   Fill/spread/financing reali (il vero motivo per usare demo), zero interferenza col reconciler.
2. **Build scope** = **vertical slice**: H2 gap-fade end-to-end PRIMA, poi plug-in H3/H4.
3. **Executor** = standalone scheduled runner (APScheduler) dietro interfaccia `ForwardStrategy`
   pulita, così il loop persistente (per H4) potrà ospitare la stessa strategia più avanti.
4. **Universe H2** = **CFD azioni US liquide** (AAPL, NVDA, TSLA, MSFT, AMD…), NON indici 24h
   (un CFD indice 24h non ha gap: tradea in continuo; il gap vero è sull'azione cash-session).
5. **Sizing** = notional fisso uniforme **$200**/trade, NO compounding, NO martingale.
6. **Kill** = a **N≥100 trade**, giudizio Sharpe-forward/t-stat/DSR; kill se CI⊇0 o net≤0 a costi reali.

## 4. Architettura — componenti (unità isolate)

| Unità | Responsabilità | Dipende da |
|---|---|---|
| `ForwardStrategy` (ABC) | Interfaccia: `should_enter(ctx)→Signal\|None`, `exit_rule(pos,ctx)→bool`, meta (universe, calendario sessione, sizing) | — |
| `GapFadeStrategy` | Implementa H2 (calcolo gap, soglia, direzione fade, SL, regole exit) | `ForwardStrategy` |
| `ExperimentExecutor` | Possiede la **propria** sessione broker pinnata all'accountId esperimento; piazza/chiude ordini; impone sizing + SL hard + cap concorrenti + daily-loss-limit | broker client esistente |
| `ForwardLedger` | Record per-trade: entry/exit ts, epic, side, px, size, sl, gross, costi, **net (da broker)**, **tesi d'entrata**. SQLite/CSV in `data/forward_lab/` (gitignored) | — |
| `ExperimentScheduler` | APScheduler: trigger apertura-sessione per strumento + pass mark/reconcile periodico + flatten EOD | `ExperimentExecutor`, `ForwardStrategy` |
| `ForwardScorer` | Legge ledger → stats per-ipotesi (riusa `factory_stats`) → verdetto kill/promote | `ForwardLedger`, `factory_stats` |
| **Isolation guard** | `assert active_account == EXPERIMENT_ACCOUNT_ID != SOAK_ACCOUNT` PRIMA di ogni ordine | — |

## 5. Data flow (H2)

```
trigger apertura-sessione (scheduler)
  → executor snapshot: prev_close, today_open (broker get_market_details / candles)
  → GapFadeStrategy.should_enter: gap = open/prev_close − 1; se |gap| > soglia → Signal(fade)
  → executor: ordine MARKET sull'account esperimento + SL hard broker-side
  → ForwardLedger.record_open(tesi, entry, sl, size)
  → pass mark periodico: polla posizioni account esperimento
       on 50%-gap-fill | SL | EOD-flatten → close
  → net P&L SOLO da broker Transaction.size/Position.upl (MAI (exit−entry)*size)
  → ForwardLedger.record_close → ForwardScorer aggrega
```

## 6. Isolamento & safety (il vincolo critico)

- **Sessione broker indipendente**: il lab crea la **propria** sessione (CST/token propri),
  switchata UNA volta all'accountId esperimento allo startup. NON condivide mai la sessione del
  soak (`paper_loop`). Switch via Capital.com account-switch (`PUT /session` accountId —
  *confermare endpoint in impl*).
- **Invisibilità reciproca**: `paper_loop.list_positions()` è **account-scoped** → non vede mai
  le posizioni esperimento, e viceversa. È il guadagno pulito dell'account separato: nessun tag,
  nessuna modifica al loop di produzione.
- **Kill-switch + daily-loss-limit** scoped all'account esperimento (mirror di emergency-stop,
  ristretto al lab).
- **Rispetta invarianti** (CLAUDE.md): P&L solo da broker; SL hard sempre; close-detection riusa
  i tier di `close_detector`; `datetime.now(timezone.utc).replace(tzinfo=None)` su write Postgres.

## 7. Sizing & kill protocol (condiviso)

- Notional fisso **$200**/trade, uniforme → ogni trade = peso-info uguale. NO compounding/martingale.
- **SL hard broker-side** su OGNI trade (cap dell'asimmetria — vitale per H4).
- Cap posizioni concorrenti (default **5**). Daily-loss-limit → halt giornata.
- **Falsificazione per ipotesi**: a N≥100 trade, calcola Sharpe-forward + t-stat + DSR
  (`factory_stats`). **Kill** se CI bootstrap ⊇ 0 OPPURE net ≤ 0 a costi reali. **Promote**
  sopravvissuti a sample più grande / spread reale.

## 8. H2 `GapFadeStrategy` — regole concrete

| Param | Valore (default, tunabile) |
|---|---|
| Universe | CFD azioni US liquide (lista epic configurabile; start ~8–12 nomi) |
| Gap | `open / prev_close − 1` all'apertura cash-session |
| Soglia entry | `|gap| > 1%` |
| Direzione | gap-up → **short**, gap-down → **long** (fade) |
| Entry | market alla/subito dopo apertura, size $200 |
| SL hard | oltre l'estensione gap (es. entry ± `k`×ATR o `m`% oltre open) |
| Exit | **50% gap-fill** OR **EOD flatten** (time-stop a chiusura sessione) OR **SL** |
| Falsifica | net-of-cost forward < break-even, o i gap "corrono" più di quanto rientrano |

## 9. Track parallelo: screen backtest H1/H5 (indipendente)

Script standalone in `scripts/ab/` (convenzione `test_*.py` + `harness.py`), NO broker, NO forward:

- `test_rsi2.py` (H1): RSI(2) su close daily + filtro MA200 → weight matrix → `DailyBacktester.run`
  con split OOS. Verdetto: edge OOS net? Atteso decay post-2010 → conferma a costo zero.
- `test_overnight.py` (H5): da OHLC daily, `overnight_ret = open/prev_close − 1`; sottrai
  `OVERNIGHT_RATES` (financing); Sharpe/segno. **Kill economico in 1 calcolo** se net ≤ 0.

Sopravvissuti → graduano nel forward lab accanto a H2/H3/H4. Indipendenti dal lab → parallelizzabili.

## 10. Testing

- **Unit**: `GapFadeStrategy.should_enter` (matematica gap, soglia, direzione — pure fn, table tests);
  `ForwardLedger` round-trip; `ForwardScorer` vs serie nota; **isolation guard rifiuta accountId soak**.
- **Integration**: `ExperimentExecutor` in **dry-run** (logga ordini intenzionali senza inviarli)
  validato PRIMA di qualsiasi ordine live; poi un singolo ordine live demo verificato (place→fill→close).
- H1/H5 screen: assert su serie sintetiche con edge noto.

## 11. Fasi / roadmap

1. **Fase 1 (questo spec)** — harness skeleton + `GapFadeStrategy` (H2) end-to-end, dry-run → live demo.
   In parallelo: screen H1/H5.
2. **Fase 2** — plug-in H3 (ORB) sotto la stessa interfaccia.
3. **Fase 3** — loop persistente (executor #2) + H4 spike-fade (con guardrail tail-risk rinforzati).

## 12. Da confermare in implementazione

- Endpoint Capital.com account-switch + come si provisiona/identifica l'**accountId esperimento**
  (il dedicato demo).
- Epic + orari cash-session degli stock CFD US su Capital.com demo (apertura per il trigger H2).
- Classe/percorso esatto del broker client + session manager da riusare.
- Pattern APScheduler per la cadenza (già in uso da `PnlSnapshotScheduler`) — da riusare.

## 13. File layout (previsto)

```
backend/scripts/ab/forward_lab.py        # CLI entry (run|status|score) + ExperimentScheduler
backend/scripts/ab/forward/strategy.py   # ForwardStrategy ABC + GapFadeStrategy
backend/scripts/ab/forward/executor.py   # ExperimentExecutor + isolation guard
backend/scripts/ab/forward/ledger.py     # ForwardLedger
backend/scripts/ab/forward/scorer.py     # ForwardScorer (riusa factory_stats)
backend/scripts/ab/test_rsi2.py          # H1 screen (parallelo)
backend/scripts/ab/test_overnight.py     # H5 screen (parallelo)
data/forward_lab/                        # ledger per-trade (gitignored)
```

## 14. Isolamento validato — 2026-06-03

`validate-isolation` = **ISOLATION OK**. Setup finale: **stesso account Capital.com**, **API key dedicata** per l'esperimento (sessione/CST separata dalla soak; creds in `.env` `CAPITAL_EXPERIMENT_*`). Il conto-attivo Capital.com è **per-sessione**: lo switch della sessione esperimento a **'USDd'** (`16772336922734878`) NON sposta la sessione soak (resta su **'Account test'** `322643372115580062`). Soak e esperimento girano simultaneamente, isolati. Verde per ordini live sul conto 'USDd'. (Il piano prevedeva il login separato come fallback; non necessario — la key dedicata + per-session switch basta.)
