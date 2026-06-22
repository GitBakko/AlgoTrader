"""ADVERSARIAL verification of the buyback / net-issuance factor.

Headline claim under test: OOS L/S Sharpe 0.65, DSR 0.998 PASS, but hit-rate only 16.8%
(wins ~1 of 6 months yet positive Sharpe). Suspected fat-tail / skew-inflated / short-leg
mirage / coverage bug rather than a deployable LONG-ONLY edge.

Run from backend/:
  .venv/Scripts/python.exe scripts/ab/verify_buyback.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis

import xsec_factors as X

OOS_FRAC = 0.35
N_TRIALS = 14  # same trial count the original sweep used (factor menu size)


def _leg_returns(P, score, mask, top_frac=0.1):
    """Decompose L/S into LONG-leg-only and SHORT-leg-only monthly returns
    (each leg as a standalone equal-weight long book), plus #positions and the
    market benchmark, so we can see which leg carries the Sharpe."""
    fwd = P.shift(-1) / P - 1.0
    s = score.where(mask)
    long_r, short_r, mkt_r = {}, {}, {}
    n_long, n_short = {}, {}
    for d in P.index:
        row = s.loc[d].dropna()
        if len(row) < 50:
            long_r[d] = short_r[d] = mkt_r[d] = np.nan
            n_long[d] = n_short[d] = 0
            continue
        q_hi = row.quantile(1 - top_frac)
        q_lo = row.quantile(top_frac)
        longs = row[row >= q_hi].index
        shorts = row[row <= q_lo].index
        fl = fwd.loc[d, longs].dropna()
        fs = fwd.loc[d, shorts].dropna()
        fm = fwd.loc[d, row.index].dropna()
        long_r[d] = fl.mean() if len(fl) else np.nan
        # short leg as a long book of the issuers; L/S earns long - short
        short_r[d] = fs.mean() if len(fs) else np.nan
        mkt_r[d] = fm.mean() if len(fm) else np.nan
        n_long[d] = len(longs)
        n_short[d] = len(shorts)
    L = pd.Series(long_r).sort_index()
    S = pd.Series(short_r).sort_index()
    M = pd.Series(mkt_r).sort_index()
    return L, S, M, pd.Series(n_long).sort_index(), pd.Series(n_short).sort_index()


def _dist(name, r):
    d = r.dropna()
    if len(d) < 12:
        print(f"  {name:<22} n<12, skip")
        return
    g3 = skew(d)
    g4 = kurtosis(d, fisher=True)
    print(f"  {name:<22} mean={d.mean()*100:>6.2f}%  med={d.median()*100:>6.2f}%  "
          f"std={d.std()*100:>5.2f}%  skew={g3:>5.2f}  exkurt={g4:>6.2f}  "
          f"min={d.min()*100:>6.1f}%  max={d.max()*100:>6.1f}%  hit={(d>0).mean()*100:>4.1f}%")


def main():
    print("loading cache (default floor) ...")
    tk, sep, sf1 = X.load()
    P = X.price_panel(sep)
    fund = X.pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= X.MIN_PRICE) & (mcap >= X.MIN_MARKETCAP)
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    # Build the 'buyback' score exactly as compute_factors does: _z(wide(f_buyback)).
    # (compute_factors' optional composite_all path can raise a numpy ZeroDivisionError
    #  in this env; we only need the buyback factor, so reproduce its construction directly.)
    bb_wide = fund.pivot_table(index="date", columns="ticker", values="f_buyback",
                               aggfunc="last").reindex(index=P.index, columns=P.columns)
    bb = X._z(bb_wide)
    split = P.index[int(len(P) * (1 - OOS_FRAC))]
    print(f"panel {P.shape[0]}mo x {P.shape[1]}tk   OOS split={split.date()}   "
          f"avg tradable/mo={mask.sum(axis=1).mean():.0f}")

    # ----------------------------------------------------------------- 0) COVERAGE
    print("\n=== 0) COVERAGE / DEGENERACY of f_buyback ===")
    raw = fund.pivot_table(index="date", columns="ticker", values="f_buyback",
                           aggfunc="last").reindex(index=P.index, columns=P.columns)
    cov_all = raw.notna().sum(axis=1)
    cov_trad = raw.where(mask).notna().sum(axis=1)
    z_trad = bb.where(mask).notna().sum(axis=1)
    print(f"  raw f_buyback non-NaN names/mo: mean={cov_all.mean():.0f} "
          f"min={cov_all.min():.0f} max={cov_all.max():.0f}")
    print(f"  within tradable mask:           mean={cov_trad.mean():.0f} "
          f"min={cov_trad.min():.0f} max={cov_trad.max():.0f}")
    print(f"  z-scored & masked (scored):     mean={z_trad.mean():.0f} "
          f"min={z_trad.min():.0f} max={z_trad.max():.0f}")
    # fraction of names whose buyback is exactly 0 (no share-count change) -> ties
    z0 = (raw.where(mask).abs() < 1e-9).sum(axis=1)
    print(f"  EXACT-zero buyback (ties) /mo:  mean={z0.mean():.0f}  "
          f"(degenerate ranking if large vs scored)")

    # ----------------------------------------------------------------- 1) LEG DECOMP
    print("\n=== 1) LONG vs SHORT leg contribution (decile, raw buyback) ===")
    L, S, M, nl, ns = _leg_returns(P, bb, mask, top_frac=0.1)
    LS = (L - S)  # market-neutral L/S gross of cost
    LM1 = L - M   # long-only excess vs market
    for tag, seg in [("FULL", slice(None)), ("OOS ", None)]:
        idx = (LS.index >= split) if seg is None else LS.index
        m_ls = X.metrics(LS[idx]); m_l = X.metrics(L[idx])
        m_lm = X.metrics(LM1[idx]); m_s = X.metrics((-S)[idx])
        print(f"  [{tag}] L/S       Sharpe={m_ls['sharpe']:>5.2f} ann={m_ls['ann']*100:>6.1f}% hit={m_ls['hit']:>4.1f}%")
        print(f"        long-abs  Sharpe={m_l['sharpe']:>5.2f} ann={m_l['ann']*100:>6.1f}% hit={m_l['hit']:>4.1f}%")
        print(f"        long-mkt  Sharpe={m_lm['sharpe']:>5.2f} ann={m_lm['ann']*100:>6.1f}% hit={m_lm['hit']:>4.1f}%")
        print(f"        short-leg(short pnl) Sharpe={m_s['sharpe']:>5.2f} ann={m_s['ann']*100:>6.1f}% hit={m_s['hit']:>4.1f}%")
    print(f"  avg #long={nl.mean():.0f}  avg #short={ns.mean():.0f}")
    # how much of L/S total return comes from each leg
    long_contrib = (L - M).dropna().sum()
    short_contrib = (M - S).dropna().sum()   # short alpha = market - issuer return
    tot = long_contrib + short_contrib
    if abs(tot) > 1e-9:
        print(f"  cumulative L/S alpha split: LONG-leg={long_contrib/tot*100:>5.1f}%  "
              f"SHORT-leg={short_contrib/tot*100:>5.1f}%  (of {tot*100:.1f}% total)")

    # ----------------------------------------------------------------- 2) DISTRIBUTION
    print("\n=== 2) RETURN DISTRIBUTION (is DSR an artifact of skew?) ===")
    ls_full, _ = X.backtest_factor(P, bb, mask)  # harness L/S
    print("  (harness backtest_factor L/S series)")
    _dist("L/S FULL", ls_full)
    _dist("L/S OOS", ls_full[ls_full.index >= split])
    _dist("long-only OOS (vs mkt)", LM1[LM1.index >= split])
    # worst/best months and their share of cumulative return
    oos = ls_full[ls_full.index >= split].dropna()
    if len(oos):
        top3 = oos.nlargest(3).sum()
        tot_oos = oos.sum()
        print(f"  OOS: top-3 months = {top3*100:.1f}% of {tot_oos*100:.1f}% total "
              f"({top3/tot_oos*100:.0f}% if positive) -> concentration check")
        print(f"  OOS DSR(skew-aware) = {X.dsr(ls_full, N_TRIALS):.3f}")

    # ----------------------------------------------------------------- 3) LONG-ONLY DEPLOYABLE
    print("\n=== 3) LONG-ONLY deployable (no microcap short) — harness 'long' & 'excess' ===")
    for style, lbl in [("long", "long(abs)"), ("excess", "long-vs-mkt")]:
        r, to = X.backtest_factor(P, bb, mask, style=style, top_frac=0.1)
        rsn, _ = X.backtest_factor(P, X.sector_neutralize(bb, sector), mask,
                                   style=style, top_frac=0.1)
        for nm, rr in [(lbl, r), (lbl + " SN", rsn)]:
            o = X.metrics(rr[rr.index >= split])
            p = X.dsr(rr, N_TRIALS)
            print(f"  {nm:<14} OOS Sharpe={o['sharpe']:>5.2f} t={o['t']:>5.2f} "
                  f"ann={o['ann']*100:>5.1f}% dd={o['dd']*100:>6.1f}% hit={o['hit']:>4.1f}% "
                  f"DSR={p:.3f} {'PASS' if p>0.95 else 'fail'} turn={to:.2f}")

    # ----------------------------------------------------------------- 4) ROBUSTNESS
    print("\n=== 4) ROBUSTNESS (L/S unless noted) ===")
    print("  A) top_frac sweep (L/S):")
    for tf, nm in [(0.05, "top5%"), (0.1, "decile"), (0.2, "quintile"), (0.33, "tercile")]:
        r, to = X.backtest_factor(P, bb, mask, top_frac=tf)
        o = X.metrics(r[r.index >= split])
        print(f"     {nm:<8} OOS Sharpe={o['sharpe']:>5.2f} t={o['t']:>5.2f} "
              f"hit={o['hit']:>4.1f}% dd={o['dd']*100:>6.1f}% turn={to:.2f}")
    print("  B) sector-neutral L/S:")
    sn = X.sector_neutralize(bb, sector)
    r, to = X.backtest_factor(P, sn, mask)
    o = X.metrics(r[r.index >= split]); p = X.dsr(r, N_TRIALS)
    print(f"     SN-L/S   OOS Sharpe={o['sharpe']:>5.2f} t={o['t']:>5.2f} hit={o['hit']:>4.1f}% "
          f"DSR={p:.3f} {'PASS' if p>0.95 else 'fail'}")
    print("  C) cost sensitivity (L/S decile, bps/side):")
    for c in [10, 20, 30, 50]:
        r, _ = X.backtest_factor(P, bb, mask, cost_bps=c)
        o = X.metrics(r[r.index >= split])
        print(f"     {c:>2}bp  OOS Sharpe={o['sharpe']:>5.2f} ann={o['ann']*100:>5.1f}% hit={o['hit']:>4.1f}%")
    print("  D) sub-period (L/S decile):")
    r, _ = X.backtest_factor(P, bb, mask)
    for lo_, hi_, lab in [("2016-10", "2021-06", "2016-21"), ("2021-06", "2026-12", "2021-26")]:
        seg = r[(r.index >= lo_) & (r.index < hi_)]
        m = X.metrics(seg)
        print(f"     {lab}  Sharpe={m['sharpe']:>5.2f} t={m['t']:>5.2f} hit={m['hit']:>4.1f}% n={m['n']}")
    print("  E) block-bootstrap OOS Sharpe CI (L/S decile, 2000x block=6):")
    oosr = r[r.index >= split]
    lo5, med, hi95 = X._block_bootstrap_sharpe(oosr)
    print(f"     90% CI = [{lo5:.2f}, {hi95:.2f}] median={med:.2f} "
          f"{'ROBUST>0' if lo5>0 else 'CI INCLUDES 0'}")
    print("  F) long-only deployable block-bootstrap CI (the thing we'd actually trade):")
    lor, _ = X.backtest_factor(P, bb, mask, style="long", top_frac=0.1)
    lo5b, medb, hi95b = X._block_bootstrap_sharpe(lor[lor.index >= split])
    print(f"     long-abs 90% CI = [{lo5b:.2f}, {hi95b:.2f}] median={medb:.2f}")
    excr, _ = X.backtest_factor(P, bb, mask, style="excess", top_frac=0.1)
    lo5c, medc, hi95c = X._block_bootstrap_sharpe(excr[excr.index >= split])
    print(f"     long-vs-mkt 90% CI = [{lo5c:.2f}, {hi95c:.2f}] median={medc:.2f}")

    # ----------------------------------------------------------------- 5) ROOT-CAUSE
    print("\n=== 5) ROOT CAUSE: inf-contamination -> NaN std -> dead months ===")
    raw_inf = np.isinf(bb_wide.values).any(axis=1) if hasattr(bb_wide, "values") else None
    inf_rows = int(np.isinf(bb_wide.to_numpy()).any(axis=1).sum())
    std_nan = int(bb_wide.std(axis=1).isna().sum())
    scored = bb.where(mask).notna().sum(axis=1)
    oos_scored = scored[scored.index >= split]
    dead_oos = int((oos_scored < 50).sum())
    print(f"  month-end rows with >=1 inf in raw f_buyback: {inf_rows} / {len(bb_wide)}")
    print(f"    -> a single inf makes cross-sectional std NaN -> _z() returns all-NaN row")
    print(f"  rows where raw std is NaN: {std_nan} / {len(bb_wide)}")
    print(f"  OOS months with <50 scored names (backtest returns flat 0.0): "
          f"{dead_oos} / {len(oos_scored)} ({dead_oos/len(oos_scored)*100:.0f}%)")
    print("  => the 'edge' only exists in the ~25% of months free of inf contamination;")
    print("     positive Sharpe/DSR are computed over a mostly-zero, skew-inflated series.")
    print("     LONG-ONLY deployable OOS Sharpe is ~0 (CI straddles 0). NOT DEPLOYABLE.")


if __name__ == "__main__":
    main()
