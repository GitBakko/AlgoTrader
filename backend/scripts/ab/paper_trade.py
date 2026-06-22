"""composite3 forward PAPER-TRADE harness (Track A deploy prep — NO capital, NO broker).

Operationalizes XSEC_MOMENTUM_SPEC.md §5. Reuses the EXACT validated selection
(xsec_factors: sector-neutral composite3, top quintile, $2B/$3 universe, monthly) and
the EXACT backtest return convention (fwd = closeadj[D+1]/closeadj[D]-1, book =
fwd[longs].fillna(0).mean(); excess = book - EW-universe — the validated Sharpe-1.0 row).

Subcommands (run from backend/):
  simulate [N]   replay open->mark over the last N cached month-ends (default 24) and
                 confirm the OPERATIONAL path reproduces the backtest (book / EW / excess
                 CAGR + annualized Sharpe). This is the integrity gate, runs on cache NOW.
  open           freeze THIS month's target book into the live ledger (one forward obs).
  mark           realize every open book whose D+1 month is now in the cache; append to
                 the forward track record.
  status         print the live ledger + forward track record so far.

Ledger: data/sharadar/paper_ledger.json (open books) + paper_track_record.csv (realized).
Data + these files are gitignored (Sharadar Personal-Use licence).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
sys.stdout.reconfigure(encoding="utf-8")

from xsec_factors import (  # noqa: E402
    CACHE, MIN_PRICE, compute_factors, load, pit_fundamentals, price_panel,
    sector_neutralize,
)
from generate_portfolio import MCAP_FLOOR, select_book  # noqa: E402  canonical book selector

TRADING_MONTHS = 12
LEDGER = CACHE / "paper_ledger.json"
TRACK = CACHE / "paper_track_record.csv"


class Strategy:
    """Loads the panels once; exposes book selection + forward marking per date."""

    def __init__(self):
        tk, sep, sf1 = load()
        self.P = price_panel(sep)
        fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
        self.mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                                     aggfunc="last").reindex(index=self.P.index,
                                                             columns=self.P.columns)
        td = tk.drop_duplicates("ticker").set_index("ticker")
        self.sector = td["sicsector"]
        self.name = td["name"]
        self.industry = td["famaindustry"]
        self.score = sector_neutralize(
            compute_factors(self.P, fund, mom_lb=12)["composite3"], self.sector)
        self.fwd = self.P.shift(-1) / self.P - 1.0  # D -> D+1 realized (the label)

    def dates(self):
        return self.P.index

    def universe(self, d):
        mask = (self.P.loc[d] >= MIN_PRICE) & (self.mcap.loc[d] >= MCAP_FLOOR)
        return self.score.loc[d].where(mask).dropna()

    def book(self, d):
        """Canonical capped top-quintile holdings at month-end d (shared selector)."""
        row = self.universe(d)
        if len(row) < 50:
            return None, row
        holds = select_book(row, self.industry)
        return holds, row

    def realize(self, d):
        """Return (n, r_book, r_ew, r_excess) for the book formed at d, earned d->d+1.
        Matches backtest_factor exactly: equal-weight, fwd NaN->0 (delisted = flat)."""
        holds, uni = self.book(d)
        if holds is None:
            return None
        r_book = float(self.fwd.loc[d, holds.index].fillna(0).mean())
        r_ew = float(self.fwd.loc[d, uni.index].fillna(0).mean())
        return len(holds), r_book, r_ew, r_book - r_ew


def _ann(series: pd.Series):
    s = series.dropna()
    if len(s) < 3:
        return 0.0, 0.0, 0.0
    mean, sd = s.mean(), s.std(ddof=1)
    sharpe = mean / sd * np.sqrt(TRADING_MONTHS) if sd > 0 else 0.0
    cagr = (1 + s).prod() ** (TRADING_MONTHS / len(s)) - 1
    eq = (1 + s).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    return sharpe, cagr, dd


def cmd_simulate(strat: Strategy, n: int = 24):
    dates = [d for d in strat.dates() if not np.isnan(strat.fwd.loc[d]).all()]
    dates = dates[-n:]
    rows = []
    for d in dates:
        r = strat.realize(d)
        if r is None:
            continue
        nm, rb, re_, rx = r
        rows.append((d, nm, rb, re_, rx))
    df = pd.DataFrame(rows, columns=["date", "n", "book", "ew", "excess"]).set_index("date")
    print(f"=== INTEGRITY SIMULATION — last {len(df)} cached months "
          f"({df.index.min().date()} -> {df.index.max().date()}) ===")
    print(f"{'month':<12}{'n':>4}{'book%':>9}{'EWuni%':>9}{'excess%':>9}")
    for d, r in df.iterrows():
        print(f"{str(d.date()):<12}{int(r.n):>4}{r.book*100:>8.2f}%"
              f"{r.ew*100:>8.2f}%{r.excess*100:>8.2f}%")
    print()
    for lbl, col in [("LONG book", "book"), ("EW universe", "ew"), ("EXCESS/alpha", "excess")]:
        sh, cg, dd = _ann(df[col])
        print(f"  {lbl:<14} ann-Sharpe={sh:>5.2f}  CAGR={cg*100:>6.1f}%  maxDD={dd*100:>6.1f}%  "
              f"cum={((1+df[col]).prod()-1)*100:>6.1f}%")
    print("\nGate: EXCESS ann-Sharpe should reproduce the validated OOS ~1.0 (spec §3);"
          "\n      LONG book CAGR the ~17% (full beta). Operational path == backtest if so.")
    return df


def cmd_open(strat: Strategy):
    d = strat.dates()[-1]
    holds, uni = strat.book(d)
    if holds is None:
        print(f"only {len(uni)} scored names on {d.date()} — stale cache, abort open.")
        return
    entry = {
        "asof": str(d.date()),
        "n": int(len(holds)),
        "universe_n": int(len(uni)),
        "weight": 1.0 / len(holds),
        "tickers": list(holds.index),
        "marked": False,
    }
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else []
    if any(e["asof"] == entry["asof"] for e in ledger):
        print(f"book for {entry['asof']} already in ledger — skip.")
        return
    ledger.append(entry)
    LEDGER.write_text(json.dumps(ledger, indent=2))
    print(f"OPENED forward book {entry['asof']}: {entry['n']} names "
          f"@ {entry['weight']*100:.2f}% (universe {entry['universe_n']}). "
          f"Mark after the next month-end prints to cache.")


def cmd_mark(strat: Strategy):
    if not LEDGER.exists():
        print("no ledger — run 'open' first.")
        return
    ledger = json.loads(LEDGER.read_text())
    last_cached = strat.dates()[-1]
    track = pd.read_csv(TRACK).to_dict("records") if TRACK.exists() else []
    marked_dates = {r["asof"] for r in track}
    new = 0
    for e in ledger:
        if e["asof"] in marked_dates:
            e["marked"] = True
            continue
        d = pd.Timestamp(e["asof"])
        # need a month-end strictly AFTER d in the cache to have a realized fwd
        future = [x for x in strat.dates() if x > d]
        if not future:
            print(f"  {e['asof']}: no forward month in cache yet — hold.")
            continue
        holds = pd.Index(e["tickers"])
        r_book = float(strat.fwd.loc[d, holds.intersection(strat.P.columns)].fillna(0).mean())
        uni = strat.universe(d)
        r_ew = float(strat.fwd.loc[d, uni.index].fillna(0).mean())
        track.append({"asof": e["asof"], "n": e["n"], "book": r_book,
                      "ew": r_ew, "excess": r_book - r_ew,
                      "marked_against": str(future[0].date())})
        e["marked"] = True
        new += 1
        print(f"  MARKED {e['asof']} (vs {future[0].date()}): book {r_book*100:+.2f}%  "
              f"EW {r_ew*100:+.2f}%  excess {(r_book-r_ew)*100:+.2f}%")
    LEDGER.write_text(json.dumps(ledger, indent=2))
    if track:
        pd.DataFrame(track).to_csv(TRACK, index=False)
    print(f"{new} new observation(s) marked. track record: {len(track)} months.")


def cmd_status():
    if LEDGER.exists():
        ledger = json.loads(LEDGER.read_text())
        print(f"=== LEDGER ({len(ledger)} open books) ===")
        for e in ledger:
            print(f"  {e['asof']}  {e['n']:>3} names  marked={e['marked']}")
    else:
        print("no ledger yet.")
    if TRACK.exists():
        df = pd.read_csv(TRACK)
        print(f"\n=== FORWARD TRACK RECORD ({len(df)} months) ===")
        print(df.to_string(index=False))
        if len(df) >= 3:
            for lbl, col in [("LONG", "book"), ("EW", "ew"), ("EXCESS", "excess")]:
                sh, cg, dd = _ann(df[col])
                print(f"  {lbl:<8} ann-Sharpe={sh:5.2f} CAGR={cg*100:6.1f}% maxDD={dd*100:6.1f}%")
        else:
            print("  (need >=6-12 months of forward obs before judging — spec §5)")
    else:
        print("\nno forward track record yet — run 'mark' after a new month-end.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "simulate"
    if cmd == "status":
        cmd_status()
        return
    strat = Strategy()
    if cmd == "simulate":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        cmd_simulate(strat, n)
    elif cmd == "open":
        cmd_open(strat)
    elif cmd == "mark":
        cmd_mark(strat)
    else:
        print(f"unknown command '{cmd}' — use simulate|open|mark|status")


if __name__ == "__main__":
    main()
