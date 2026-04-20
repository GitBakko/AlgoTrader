# MANTIS AI — System Audit (2026-04-14)

Data source: PostgreSQL `positions` table, 1137 closed trades.

---

## 1. Overview

| Metric | Value |
|---|---|
| Total closed trades | 1,137 |
| Wins | 316 |
| Losses | 821 |
| **Win Rate** | **27.8%** |
| Total P&L | **-$2,559.56** |
| Avg P&L per trade | -$2.25 |
| Avg win | +$5.73 |
| Avg loss | -$4.32 |
| Current R:R config | 0.75 (since 2026-04-09) |
| Break-even WR needed (R:R 0.75) | ~57% |
| Break-even WR needed (R:R 2.0, pre-fix) | ~33% |

---

## 2. Losses by Close Reason

| Reason | Trades | P&L | Avg P&L |
|---|---|---|---|
| **SL** | 682 | -$2,949.58 | -$4.32 |
| **TP** | 304 | +$1,741.76 | +$5.73 |
| EXTERNAL | 128 | -$3.22 | -$0.03 |
| MANUAL | 11 | +$82.21 | +$7.47 |
| EMERGENCY_STOP | 10 | +$3.38 | +$0.34 |
| TIME | 1 | -$83.07 | -$83.07 |
| RECONCILIATION | 1 | -$1,351.04 | -$1,351.04 |

**Verdict**: SL hits dominate (60% of all trades). SL:TP ratio is 2.24:1 — the system stops out more than twice as often as it takes profit.

---

## 3. P&L by Asset (worst first)

| Epic | Trades | P&L | Avg P&L | Win Rate |
|---|---|---|---|---|
| ADJUSTMENT | 1 | -$1,351.04 | -$1,351.04 | 0% |
| SOLUSD | 69 | -$263.00 | -$3.81 | 25% |
| XAGUSD | 66 | -$210.93 | -$3.20 | 24% |
| WTIUSD | 81 | -$210.45 | -$2.60 | **20%** |
| NATGAS | 67 | -$194.61 | -$2.90 | 24% |
| DE40 | 120 | -$191.11 | -$1.59 | 27% |
| ETHUSD | 84 | -$176.93 | -$2.11 | 29% |
| PLATINUM | 79 | -$174.73 | -$2.21 | **13%** |
| US500 | 49 | -$159.67 | -$3.26 | 35% |
| DASHUSD | 12 | -$53.64 | -$4.47 | 25% |
| BTCUSD | 77 | -$49.37 | -$0.64 | 29% |
| NAS100 | 14 | -$43.02 | -$3.07 | 21% |
| COPPER | 50 | -$37.98 | -$0.76 | 26% |
| ICPUSD | 26 | -$24.09 | -$0.93 | 12% |
| XAUUSD | 63 | -$8.37 | -$0.13 | 40% |
| DOGUSD | 71 | +$9.14 | +$0.13 | 28% |
| NVDA | 60 | +$15.96 | +$0.27 | 37% |
| GBPUSD | 35 | +$19.47 | +$0.56 | 31% |
| USDJPY | 9 | +$142.90 | +$15.88 | **56%** |
| BNBUSD | 23 | +$186.46 | +$8.11 | 30% |
| TSLA | 81 | +$215.45 | +$2.66 | **42%** |

**Profitable assets (3/21)**: TSLA, BNBUSD, USDJPY.  
**Catastrophic WR**: PLATINUM 13%, ICPUSD 12%, WTIUSD 20%.  
**ADJUSTMENT**: single reconciliation outlier (-$1,351), not a real trade.

---

## 4. P&L by Hour (UTC)

| Hour | Trades | P&L | Notes |
|---|---|---|---|
| 00:00 | 19 | -$45.96 | |
| 01:00 | 23 | +$64.71 | |
| 02:00 | 22 | -$72.36 | |
| 03:00 | 10 | +$8.61 | |
| 04:00 | 3 | -$0.59 | |
| 05:00 | 13 | -$8.99 | |
| 06:00 | 34 | +$90.11 | Pre-EU open, best non-US slot |
| 07:00 | 61 | -$128.37 | **EU open** |
| 08:00 | 84 | -$88.91 | **EU session** |
| 09:00 | 78 | +$45.48 | |
| 10:00 | 43 | -$71.27 | |
| **11:00** | **55** | **-$1,559.56** | **Contains RECONCILIATION outlier (-$1,351)** |
| 12:00 | 83 | -$127.07 | |
| 13:00 | 115 | -$61.84 | Pre-US open |
| 14:00 | 129 | +$64.02 | **US open, only high-volume positive hour** |
| **15:00** | **124** | **-$328.34** | **US session, worst real trading hour** |
| 16:00 | 63 | +$25.40 | |
| 17:00 | 45 | -$17.06 | |
| 18:00 | 27 | -$32.21 | |
| **19:00** | **24** | **-$213.87** | **Pre-US close** |
| 20:00 | 38 | -$98.05 | |
| 21:00 | 23 | -$30.26 | |
| 22:00 | 17 | +$25.62 | |
| 23:00 | 4 | +$1.20 | |

**Worst hours** (excluding outlier): 15:00 UTC (-$328), 19:00 (-$214), 07:00 (-$128), 12:00 (-$127).  
**Pattern**: losses concentrate around market opens (07-08 EU, 15 US) and pre-close (19-20). Night crypto (00-06) is nearly flat (-$55 on 90 trades).

---

## 5. Model Status

| Group | Epics | Model Date | Features | Type |
|---|---|---|---|---|
| MR-specific | XAUUSD, BTCUSD, US500, NVDA, TSLA, DE40, ETHUSD, SOLUSD, BNBUSD, PLATINUM | 2026-04-02 | 0 (no metadata) | `xgboost_mr_*` |
| Standard retrain | COPPER, DOGUSD, EURUSD, GBPUSD, NATGAS, USDJPY, WTIUSD | 2026-04-12 | 199 | `xgboost_*` |
| Standard retrain | DASHUSD, ICPUSD, NAS100, XAGUSD | 2026-04-09 | 199 | `xgboost_*` |

**Problem**: the 10 MR-specific models from Apr 2 have no feature names in metadata (0 features listed). The Apr 9 retrain (which showed F1 0.50-0.63) was overwritten by another retrain on Apr 12 with unknown parameters.

---

## 6. System Configuration

| Setting | Value |
|---|---|
| Broker | Capital.com **DEMO** |
| Execution mode | DEMO |
| MR_PRIMARY_ENABLED | true |
| ML_PRIMARY_ENABLED | true |
| SCALP_MODE_ENABLED | false |
| SCALP_CANDLE_RESOLUTION | 4h |
| MR_MAX_HOLD_HOURS | 12 |
| SL_ATR_MULT | Per-class: stocks=1.0, crypto/commodities=1.2, forex/indices=2.0 |
| TP_MAX_ATR | Per-class: stocks=0.75, crypto/commodities=0.9, forex/indices=1.5 |
| R:R | 0.75 (uniform across classes) |
| Active epics | 18/21 (excluded: NAS100, XAGUSD, DASHUSD) |

---

## 7. Key Takeaways

1. **WR 27.8% is terminal** at any R:R ratio we've used. The system stops out 2.24x more than it takes profit.
2. **SL hits are the primary loss driver** (682/1137 trades). Not slow drawdown, not time decay — raw directional failure.
3. **Only 3/21 assets are profitable** (TSLA, BNBUSD, USDJPY). The other 18 are net losers.
4. **PLATINUM (WR 13%) and ICPUSD (WR 12%)** are doing worse than a coin flip on a 3-class problem. These models are anti-predictive.
5. **Models are inconsistent**: half are MR-specific (Apr 2, no feature metadata), half are standard 199-feature (Apr 9-12). The retrain history is unclear.
6. **Market open hours are the worst** — the MR strategy is getting chopped by volatility spikes at session boundaries.
7. **The RECONCILIATION entry (-$1,351)** is an outlier that distorts the total. Real trading P&L is -$1,209.
