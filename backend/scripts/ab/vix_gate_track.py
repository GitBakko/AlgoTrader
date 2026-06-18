"""VIX term-structure gate forward PAPER-TRACK (deploy prep — NO capital, NO broker).

Operationalizes the ONLY survivor of the documented-rules shortlist (test_vix_gate.py):
the `gate R<1.0 ma3` variant — hold US500 when MA3(VIX/VIX3M) < 1.0 (contango/calm),
step to cash otherwise. Validated 2006-2026, OOS Sharpe 0.90 vs buy&hold 0.77, DD -27%
vs -34%, bootCI[+0.32,+1.51], Deflated PSR 0.974 (Fassas-Hourvouliades SSRN 3189502).

Mirrors paper_trade.py (composite3 Track A): a contemporaneously-logged forward ledger
whose operational path is proven == the backtest by `simulate`. Low-frequency daily
long/flat — does NOT fit the intraday forward-lab N>=100 trade gate, so it lives here as
its own equity-curve-scored track.

Return convention IDENTICAL to test_vix_gate.run():
    pos_t in {0,1} from MA3(VIX/VIX3M)_t < 1.0 ; held t->t+1.
    obs_return_t+1 = pos_t * spx_ret_t+1  -  |pos_t - pos_t-1| * COST
Benchmark = buy&hold spx_ret_t+1.

Subcommands (run from backend/):
  simulate [N]   replay the last N cached days, reproduce the backtest gate vs buy&hold
                 (ann-Sharpe / CAGR / DD). Integrity gate — runs on free yfinance data NOW.
  open           freeze TODAY's gate decision (latest cached close) into the live ledger
                 (one contemporaneous forward obs). Idempotent per date.
  mark           realize every open decision whose D+1 close is now cached; append to the
                 forward track record.
  status         print the live ledger + forward track record (gate vs buy&hold) so far.

Ledger: data/vix_gate/ledger.json (open decisions) + track_record.csv (realized obs).
Data is free/public (yfinance ^VIX/^VIX3M/^GSPC) — no licence restriction.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
sys.stdout.reconfigure(encoding="utf-8")

from factory_stats import cagr, metrics  # noqa: E402

PPY = 252
COST = 2e-4  # US500 CFD half-spread per unit turnover (matches test_vix_gate)
MA = 3  # MA3 of the ratio (the validated variant)
FFILL_LIMIT = 5  # max trading days a stale ^VIX3M may be carried before refusing to gate
CACHE = ROOT / "data" / "vix_gate"
CACHE.mkdir(parents=True, exist_ok=True)
LEDGER = CACHE / "ledger.json"
TRACK = CACHE / "track_record.csv"


class Strategy:
    """Loads VIX/VIX3M/SPX once; exposes the gate decision + 1-day realized return."""

    def __init__(self):
        df = {}
        for t, name in [("^VIX", "vix"), ("^VIX3M", "vix3m"), ("^GSPC", "spx")]:
            d = yf.download(t, start="2006-01-01", progress=False, auto_adjust=False)["Close"]
            df[name] = d[d.columns[0]] if isinstance(d, pd.DataFrame) else d
        raw = pd.DataFrame(df)
        raw.index = pd.to_datetime(raw.index)
        # Anchor on the S&P trading calendar; ^VIX3M lags 1-3d on Yahoo, so carry
        # it (and ^VIX) forward (bounded) instead of dropping live S&P sessions.
        # Historically a no-op (no VIX3M gaps pre-edge) -> simulate stays identical
        # to the validated test_vix_gate run; only the live edge changes.
        spx_cal = raw["spx"].dropna().index
        P = raw.reindex(spx_cal)
        P["vix"] = P["vix"].ffill(limit=FFILL_LIMIT)
        P["vix3m"] = P["vix3m"].ffill(limit=FFILL_LIMIT)
        P = P.dropna()
        self.P = P
        self.ret = P["spx"].pct_change()
        self.ratio = P["vix"] / P["vix3m"]
        self.gate = (self.ratio.rolling(MA).mean() < 1.0).astype(float)  # 1 long / 0 flat

    def dates(self):
        return self.P.index

    def pos(self, d) -> float:
        return float(self.gate.loc[d])

    def prev_pos(self, d) -> float:
        loc = self.P.index.get_loc(d)
        return float(self.gate.iloc[loc - 1]) if loc > 0 else 0.0

    def realize(self, d):
        """(pos, gate_return, bh_return) for the decision frozen at d, earned d->d+1.
        Identical to test_vix_gate.run: pos_d*ret_{d+1} - |pos_d - pos_{d-1}|*COST."""
        loc = self.P.index.get_loc(d)
        if loc + 1 >= len(self.P.index):
            return None  # no D+1 close cached yet
        nxt = self.P.index[loc + 1]
        r_next = float(self.ret.loc[nxt])
        pos, prev = self.pos(d), self.prev_pos(d)
        gate_r = pos * r_next - abs(pos - prev) * COST
        return pos, gate_r, r_next, str(nxt.date())


def _ann(series: pd.Series):
    m = metrics(series, PPY)
    return m["sharpe"], cagr(series, PPY), m["dd"]


def cmd_simulate(strat: Strategy, n: int = 252):
    idx = strat.dates()[-(n + 1) : -1]  # need a D+1 for each, so drop the last bar
    rows = []
    for d in idx:
        r = strat.realize(d)
        if r is None:
            continue
        pos, gate_r, bh_r, _ = r
        rows.append((d, pos, gate_r, bh_r))
    df = pd.DataFrame(rows, columns=["date", "pos", "gate", "bh"]).set_index("date")
    print(
        f"=== INTEGRITY SIMULATION — last {len(df)} cached days "
        f"({df.index.min().date()} -> {df.index.max().date()}) ==="
    )
    flat_days = int((df["pos"] == 0).sum())
    print(f"flat (cash) days: {flat_days} ({flat_days/len(df)*100:.1f}%)\n")
    for lbl, col in [("GATE long/flat", "gate"), ("buy&hold", "bh")]:
        sh, cg, dd = _ann(df[col])
        print(
            f"  {lbl:<16} ann-Sharpe={sh:>5.2f}  CAGR={cg*100:>6.1f}%  maxDD={dd*100:>6.1f}%  "
            f"cum={((1+df[col]).prod()-1)*100:>7.1f}%"
        )
    print(
        "\nGate: GATE Sharpe should clear buy&hold with a shallower maxDD"
        "\n      (validated OOS 0.90 vs 0.77, DD -27% vs -34%). Operational == backtest if so."
    )
    return df


def cmd_open(strat: Strategy):
    d = strat.dates()[-1]
    pos, prev = strat.pos(d), strat.prev_pos(d)
    entry = {
        "asof": str(d.date()),
        "ratio": round(float(strat.ratio.loc[d]), 4),
        "ratio_ma3": round(float(strat.ratio.rolling(MA).mean().loc[d]), 4),
        "pos": pos,  # 1.0 = long US500, 0.0 = cash
        "prev_pos": prev,
        "state": "LONG" if pos else "FLAT",
        "marked": False,
    }
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else []
    if any(e["asof"] == entry["asof"] for e in ledger):
        print(f"decision for {entry['asof']} already in ledger — skip.")
        return
    ledger.append(entry)
    LEDGER.write_text(json.dumps(ledger, indent=2))
    print(
        f"OPENED forward decision {entry['asof']}: {entry['state']} "
        f"(ratio_ma3={entry['ratio_ma3']}). Mark after the next session close prints to cache."
    )


def cmd_mark(strat: Strategy):
    if not LEDGER.exists():
        print("no ledger — run 'open' first.")
        return
    ledger = json.loads(LEDGER.read_text())
    track = pd.read_csv(TRACK).to_dict("records") if TRACK.exists() else []
    marked = {r["asof"] for r in track}
    new = 0
    for e in ledger:
        if e["asof"] in marked:
            e["marked"] = True
            continue
        d = pd.Timestamp(e["asof"])
        if d not in strat.P.index:
            print(f"  {e['asof']}: not in cache — skip.")
            continue
        r = strat.realize(d)
        if r is None:
            print(f"  {e['asof']}: no forward session in cache yet — hold.")
            continue
        pos, gate_r, bh_r, against = r
        track.append(
            {
                "asof": e["asof"],
                "state": e["state"],
                "pos": pos,
                "gate": gate_r,
                "bh": bh_r,
                "marked_against": against,
            }
        )
        e["marked"] = True
        new += 1
        print(
            f"  MARKED {e['asof']} (vs {against}): gate {gate_r*100:+.3f}%  "
            f"buy&hold {bh_r*100:+.3f}%"
        )
    LEDGER.write_text(json.dumps(ledger, indent=2))
    if track:
        pd.DataFrame(track).to_csv(TRACK, index=False)
    print(f"{new} new observation(s) marked. track record: {len(track)} days.")


def cmd_status():
    if LEDGER.exists():
        ledger = json.loads(LEDGER.read_text())
        unmarked = [e for e in ledger if not e["marked"]]
        print(f"=== LEDGER ({len(ledger)} decisions, {len(unmarked)} awaiting mark) ===")
        for e in ledger[-8:]:
            print(
                f"  {e['asof']}  {e['state']:<4} ratio_ma3={e['ratio_ma3']}  marked={e['marked']}"
            )
    else:
        print("no ledger yet.")
    if TRACK.exists():
        df = pd.read_csv(TRACK)
        print(f"\n=== FORWARD TRACK RECORD ({len(df)} days) ===")
        if len(df) >= 5:
            for lbl, col in [("GATE", "gate"), ("buy&hold", "bh")]:
                sh, cg, dd = _ann(df[col])
                cum = ((1 + df[col]).prod() - 1) * 100
                print(
                    f"  {lbl:<10} ann-Sharpe={sh:5.2f}  CAGR={cg*100:6.1f}%  "
                    f"maxDD={dd*100:6.1f}%  cum={cum:+6.2f}%"
                )
            print(
                "\n  Gate to promote: >=60-120 forward days, GATE Sharpe >= buy&hold with "
                "shallower DD (mirrors the OOS edge). NO capital until then."
            )
        else:
            print("  (need >=60-120 forward days before judging)")
    else:
        print("\nno forward track record yet — run 'mark' after a new session close.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        cmd_status()
        return
    strat = Strategy()
    if cmd == "simulate":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 252
        cmd_simulate(strat, n)
    elif cmd == "open":
        cmd_open(strat)
    elif cmd == "mark":
        cmd_mark(strat)
    else:
        print(f"unknown command '{cmd}' — use simulate|open|mark|status")


if __name__ == "__main__":
    main()
