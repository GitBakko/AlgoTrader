"""NEW AXIS (not a funding re-sweep): cross-sectional crypto MOMENTUM, survivorship-free.

The funding-positioning kill (pit_funding.py) showed that on the honest universe the
high-funding/hot coins kept WINNING in OOS — i.e. the funding book was implicitly SHORT
cross-sectional momentum. The inverse hypothesis — LONG recent winners / SHORT recent
losers — is (a) the direct analog of our ONE validated edge (equity momentum), (b) a
genuinely new signal axis, (c) testable right now on the cached survivorship-free panel.

Same PIT universe + engine + cost as pit_funding (leak-free, OOS, DSR, bootstrap).
Signal = trailing return over `lb` days, skipping the most recent `skip` days (kill 1d
reversal microstructure). LONG top decile / SHORT bottom (L/S) AND long-only-vs-universe
(deployable form). Funding is a COST here (held positions pay/receive carry) — captured.

  GO if OOS Sharpe > 0, boot CI lower > 0, DSR > 0.95, DD tradeable.
Run: .venv/Scripts/python.exe scripts/ab/pit_momentum.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from scripts.ab.harness import normalize_book  # noqa: E402
from scripts.ab.pit_funding import (  # noqa: E402
    backtest, block_boot_ci, deflated_sr, load_panels, metrics, pit_mask, psr,
)

START = "2021-01-01"
MIN_AGE = 21
TRADING_DAYS = 365


def ls_book(score, mask, top_frac, long_only=False):
    """LONG highest score (winners), SHORT lowest (losers), within mask."""
    w = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    sc = score.where(mask)
    for dt, row in sc.iterrows():
        r = row.dropna()
        k = int(len(r) * top_frac)
        if k < 2:
            continue
        ranked = r.sort_values()
        w.loc[dt, ranked.index[-k:]] = 1.0          # highest momentum -> LONG
        if long_only:
            # long-only vs universe: net long winners, funded by flat (cash) book
            continue
        w.loc[dt, ranked.index[:k]] = -1.0           # lowest -> SHORT
    return normalize_book(w)


def main():
    price, qvol, fund = load_panels()
    price = price[price.index >= pd.Timestamp(START)]
    qvol = qvol.reindex(price.index)
    fund = fund.reindex(price.index)
    n = len(price.index)
    oos = price.index[int(n * 0.65)]
    mask = pit_mask(price, qvol, 3e6)
    avg_n = mask.sum(axis=1).mean()
    print(f"PIT universe: {price.shape[1]} symbols, avg {avg_n:.0f} tradable/day, "
          f"{price.index.min().date()}->{price.index.max().date()} OOS {oos.date()}")

    # leak-free momentum scores: return over lb days, skipping last `skip` days,
    # known at close of t (uses prices through t-skip); book at t earns t->t+1.
    def mom(lb, skip=1):
        return (price.shift(skip) / price.shift(skip + lb) - 1.0)

    configs = []
    for lb in (14, 30, 60, 90):
        configs.append((f"LS mom{lb}d dec", mom(lb), mask, 0.10, False))
    # long-only deployable form at the plateau lookback
    configs.append(("LO mom30d dec", mom(30), mask, 0.10, True))
    configs.append(("LO mom60d dec", mom(60), mask, 0.10, True))
    # short-term reversal control (lb=3, the classic crypto ST reversal) — LONG losers
    configs.append(("LS rev3d dec(*)", -mom(3, 1), mask, 0.10, False))

    print(f"\n{'config':<18}{'FULL Sh':>9}{'ann%':>7}{'boot95 CI':>17}"
          f"{'OOS Sh':>8}{'OOS t':>7}{'OOSann':>8}{'maxDD':>8}{'turn':>7}")
    trial_sh, primary = [], None
    for name, score, m, frac, lo in configs:
        w = ls_book(score, m, frac, long_only=lo)
        daily, turn = backtest(price, fund, w, capture_funding=True)
        ci = block_boot_ci(daily)
        (fn, fsh, ft, fdd, fan), (on, osh, ot, odd, oan) = metrics(daily, oos)
        trial_sh.append(fsh)
        if name == "LS mom30d dec":
            primary = daily
        ci_s = f"[{ci[0]:+.2f},{ci[2]:+.2f}]" if ci is not None else "n/a"
        print(f"{name:<18}{fsh:>9.2f}{fan*100:>6.0f}%{ci_s:>17}"
              f"{osh:>8.2f}{ot:>7.2f}{oan*100:>7.0f}%{fdd*100:>7.0f}%{turn.mean():>7.2f}")
    dsr, sr0 = deflated_sr(primary, trial_sh, n_trials=max(8, len(configs)))
    print(f"\nDeflated SR* (N={max(8,len(configs))}) = {sr0:.2f}  "
          f"-> Deflated PSR (LS mom30d) = {dsr:.3f}")
    print("(*) rev3d = short-term reversal control (LONG losers); positive => MR not mom.")
    print("\nGO if OOS Sharpe>0 + boot CI lower>0 + DSR>0.95 + DD tradeable.")


if __name__ == "__main__":
    main()
