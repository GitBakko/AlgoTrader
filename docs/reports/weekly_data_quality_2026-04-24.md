# Weekly Data Quality — 2026-04-24

Window: last 7 days. Generated: 2026-04-24T14:43:07.870473+00:00

**Status**: anomalies — stale_recent=537, arith_suspects=22, swap_gaps=18

---

## UNRECONCILED (pnl=NULL)

- total: 0
- clean

## Recent STALE_CLEANUP (last 7d)

- count: 537
- **anomaly** — loop is flagging positions as stale

## OPEN positions older than 7 days

- count: 0
- clean

## Arithmetic-fallback suspects (exit==entry)

- count: 22
- **anomaly** — exit==entry + known pnl is a historical arithmetic fallback symptom
  - `00396101-0055-311e-0000-000080bf5947` NVDA reason=SL entry=202.0700
  - `00018387-0055-311e-0000-000081d8291c` NATGAS reason=SL entry=2.7484
  - `000940dd-0055-311e-0000-0000833cb4f3` BTCUSD reason=SL entry=77750.1500
  - `00513301-0055-311e-0000-000081652aa8` TSLA reason=SL entry=373.1400
  - `00396101-0055-311e-0000-000080bf5629` NVDA reason=TP entry=199.6000
  - `00513301-0055-311e-0000-00008165297c` TSLA reason=TP entry=379.1200
  - `00396101-0055-311e-0000-000080bf55d8` NVDA reason=TP entry=201.3900
  - `00513301-0055-311e-0000-0000816521d1` TSLA reason=TP entry=379.3700
  - `00513301-0055-311e-0000-000081651d0f` TSLA reason=TP entry=376.5800
  - `00018387-0055-311e-0000-000081d81c2f` NATGAS reason=TP entry=2.8719

## Swap snapshot gaps (last 7d, 7 expected/epic)

- epics with gaps: 18
- **anomaly** — scheduler not writing every day
  - XAUUSD: 1/7 rows (missing 6)
  - BTCUSD: 1/7 rows (missing 6)
  - US500: 1/7 rows (missing 6)
  - WTIUSD: 1/7 rows (missing 6)
  - EURUSD: 1/7 rows (missing 6)
  - NVDA: 1/7 rows (missing 6)
  - TSLA: 1/7 rows (missing 6)
  - DE40: 1/7 rows (missing 6)
  - SOLUSD: 1/7 rows (missing 6)
  - ETHUSD: 1/7 rows (missing 6)
  - BNBUSD: 1/7 rows (missing 6)
  - DOGUSD: 1/7 rows (missing 6)
