"""Leak-free cross-sectional equity-factor backtester on Sharadar (the hypothesis
space N=18 never let us test). Monthly rebalance, decile long-short, PIT fundamentals,
survivorship-free universe, real costs, IS-old vs OOS-recent split + Deflated Sharpe.

THE QUESTION: do cross-sectional factors (value/quality/momentum/low-vol/size) survive
OOS-recent, or are they decayed like every time-series lead we killed?

Leak discipline:
- A factor at month-end D uses ONLY data with timestamp <= D (price history <= D;
  SF1 rows with datekey <= D via merge_asof). The portfolio formed at D earns the
  return D -> D+1month. No future bar/filing is ever read.
- Universe at D = names with a valid adjusted close at D (delisted names live in the
  data with real history up to delisting, so the universe is survivorship-free; a name
  that vanishes next month simply has a NaN forward return and drops that month).

Run from backend/ (after fetch_sharadar.py):
  .venv/Scripts/python.exe scripts/ab/xsec_factors.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "sharadar"

# realistic universe filters (avoid illiquid micro-caps that you can't actually trade)
MIN_PRICE = 3.0          # USD, drop penny stocks
MIN_MARKETCAP = 200e6    # USD, small-cap floor (still ~2-3k names)
N_DECILES = 10
COST_BPS_ONEWAY = 10.0   # 10 bps per side (equity round-trip ~20bps; conservative)
TRADING_MONTHS = 12


# ---------------------------------------------------------------- loading
def load():
    tk = pd.read_parquet(CACHE / "tickers.parquet")
    sep = pd.read_parquet(CACHE / "sep_monthly.parquet")
    sf1 = pd.read_parquet(CACHE / "sf1_arq.parquet")
    sep["date"] = pd.to_datetime(sep["date"]).astype("datetime64[ns]")
    sf1["datekey"] = pd.to_datetime(sf1["datekey"]).astype("datetime64[ns]")
    if "gp" in sf1.columns and "ncfo" in sf1.columns:  # expanded schema -> derive factors
        sf1 = derive_sf1_factors(sf1)
    return tk, sep, sf1


def derive_sf1_factors(sf1: pd.DataFrame) -> pd.DataFrame:
    """Add per-ticker derived fundamental factors to SF1 (leak-safe: each filing uses
    only that filing + the same ticker's PRIOR filings, via shift within ticker on
    datekey order). New columns are then asof-joined like any other field."""
    df = sf1.sort_values(["ticker", "datekey"]).copy()
    g = df.groupby("ticker", group_keys=False)

    def lag(col, n=4):  # 4 quarters ~ 1yr (ARQ)
        return g[col].shift(n)

    a = df["assets"].replace(0, np.nan)
    aavg = df["assetsavg"].replace(0, np.nan)
    aavg = aavg.fillna(a)  # assetsavg can be sparse on ARQ -> fall back to assets
    # Novy-Marx gross profitability
    df["f_gp_assets"] = df["gp"] / a
    # Sloan accruals (low = good -> negative sign baked in)
    df["f_accruals"] = -((df["netinc"] - df["ncfo"]) / aavg)
    # Cooper asset growth (low = good)
    df["f_asset_growth"] = -(df["assets"] / lag("assets") - 1.0)
    # net share issuance / buyback (share count shrinking = good)
    df["f_buyback"] = -(df["shareswa"] / lag("shareswa") - 1.0)
    # net equity issuance via cashflow (negative ncfcommon = buyback = good)
    df["f_net_issuance"] = -(df["ncfcommon"] / df["marketcap"].replace(0, np.nan))
    # investment (capex/assets, low = good)
    df["f_low_invest"] = -(df["capex"].abs() / a)
    # Piotroski F-score (9 binary signals), needs deltas vs 1yr prior
    droa = df["roa"] - lag("roa")
    ddebt = df["debt"] / a - (lag("debt") / lag("assets"))
    dcr = df["currentratio"] - lag("currentratio")
    dshares = df["shareswa"] - lag("shareswa")
    dgm = df["grossmargin"] - lag("grossmargin")
    dat = df["assetturnover"] - lag("assetturnover")
    f = (
        (df["roa"] > 0).astype(int) + (df["ncfo"] > 0).astype(int)
        + (droa > 0).astype(int) + (df["ncfo"] > df["netinc"]).astype(int)
        + (ddebt < 0).astype(int) + (dcr > 0).astype(int)
        + (dshares <= 0).astype(int) + (dgm > 0).astype(int) + (dat > 0).astype(int)
    )
    df["f_piotroski"] = f.astype(float)
    # sanitize inf (e.g. lag==0 divisions) -> NaN so they don't poison cross-sectional z
    fcols = [c for c in df.columns if c.startswith("f_")]
    df[fcols] = df[fcols].replace([np.inf, -np.inf], np.nan)
    return df


def price_panel(sep: pd.DataFrame) -> pd.DataFrame:
    """Wide [month_end x ticker] adjusted close."""
    p = sep.pivot_table(index="date", columns="ticker", values="closeadj", aggfunc="last")
    return p.sort_index()


def pit_fundamentals(price_long: pd.DataFrame, sf1: pd.DataFrame) -> pd.DataFrame:
    """For every (ticker, month_end) attach the LATEST filing with datekey<=month_end."""
    left = price_long[["date", "ticker"]].sort_values("date")
    right = sf1.sort_values("datekey")
    merged = pd.merge_asof(
        left, right, left_on="date", right_on="datekey", by="ticker",
        direction="backward",
    )
    return merged


# ---------------------------------------------------------------- factors
def compute_factors(P: pd.DataFrame, fund: pd.DataFrame, mom_lb: int = 12) -> dict[str, pd.DataFrame]:
    """Return dict factor_name -> wide [date x ticker] score (higher = expected better)."""
    dates, tickers = P.index, P.columns
    # momentum (mom_lb)-1 (return from t-mom_lb to t-1, skip last month)
    mom = P.shift(1) / P.shift(mom_lb) - 1.0
    # low-vol: negative of trailing 12m monthly-return std (higher score = lower vol)
    rets = P.pct_change()
    lowvol = -rets.rolling(12, min_periods=6).std()

    # fundamentals -> wide frames aligned to P
    def wide(col):
        return fund.pivot_table(index="date", columns="ticker", values=col,
                                aggfunc="last").reindex(index=dates, columns=tickers)

    pe = wide("pe"); pb = wide("pb"); roe = wide("roe")
    gm = wide("grossmargin"); de = wide("de"); mcap = wide("marketcap")
    # value: earnings yield (1/pe, only positive PE) + book-to-price (1/pb)
    ey = (1.0 / pe).where(pe > 0)
    bp = (1.0 / pb).where(pb > 0)
    value = _combine(_z(ey), _z(bp))
    # quality: roe + gross margin - leverage (nan-tolerant: banks lack grossmargin etc.)
    quality = _combine(_z(roe), _z(gm), _z(-de))
    # size: small = high score (negative log mktcap)
    size = _z(-np.log(mcap.where(mcap > 0)))
    # price-based extras
    st_reversal = -(P / P.shift(1) - 1.0)                       # 1m reversal (low ret = good)
    high52 = P / P.shift(1).rolling(12, min_periods=6).max()    # nearness to 12m high

    factors = {
        "value": value, "quality": quality, "momentum": _z(mom),
        "lowvol": _z(lowvol), "size": size,
        "st_reversal": _z(st_reversal), "high52w": _z(high52),
    }
    # derived fundamental factors (present only with expanded SF1 schema)
    for key, col in [("gross_profit", "f_gp_assets"), ("accruals", "f_accruals"),
                     ("asset_growth", "f_asset_growth"), ("buyback", "f_buyback"),
                     ("net_issuance", "f_net_issuance"), ("low_invest", "f_low_invest"),
                     ("piotroski", "f_piotroski")]:
        if col in set(fund.columns):
            factors[key] = _z(wide(col))

    # composites
    factors["composite3"] = _combine(value, quality, _z(mom))   # the validated v1 (value+qual+mom)
    if "gross_profit" in factors:
        factors["composite_all"] = _combine(
            value, factors["gross_profit"], _z(mom), factors["accruals"],
            factors["asset_growth"], factors["buyback"])
    return factors


def sector_neutralize(score: pd.DataFrame, sector: pd.Series) -> pd.DataFrame:
    """Demean each row WITHIN sector (per date) so ranking is relative-to-sector.
    Removes sector bets: the top decile then draws the best-vs-peers from every sector."""
    out = score.copy()
    secs = sector.reindex(out.columns).fillna("UNKNOWN")
    for s in secs.unique():
        cols = secs.index[secs == s]
        cols = [c for c in cols if c in out.columns]
        if len(cols) < 5:
            continue
        grp = out[cols]
        out[cols] = grp.sub(grp.mean(axis=1), axis=0)
    return out


def _combine(*frames: pd.DataFrame) -> pd.DataFrame:
    """Element-wise nan-tolerant mean of z-scored frames (a name missing one
    component is still scored on the others; only all-NaN -> NaN)."""
    arr = np.stack([f.values.astype(float) for f in frames])
    cnt = np.sum(~np.isnan(arr), axis=0)
    tot = np.nansum(arr, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(cnt > 0, tot / cnt, np.nan)
    return pd.DataFrame(m, index=frames[0].index, columns=frames[0].columns)


def _z(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score per row (winsorized at +/-3)."""
    mu = df.mean(axis=1)
    sd = df.std(axis=1)
    z = df.sub(mu, axis=0).div(sd.replace(0, np.nan), axis=0)
    return z.clip(-3, 3)


# ---------------------------------------------------------------- backtest
def backtest_factor(P: pd.DataFrame, score: pd.DataFrame, mask: pd.DataFrame,
                    cost_bps: float = COST_BPS_ONEWAY, long_only: bool = False,
                    top_frac: float = 1.0 / N_DECILES, style: str | None = None):
    """top_frac portfolio, equal-weight, monthly. style:
    'ls'     = top frac long + bottom frac short (market-neutral L/S).
    'excess' = long top frac, short the equal-weight universe (active return vs market).
    'long'   = pure long top frac, fully invested (ABSOLUTE deployable return).
    (long_only=True kept as alias for 'excess'.)
    Returns (net monthly series, avg turnover)."""
    if style is None:
        style = "excess" if long_only else "ls"
    fwd = P.shift(-1) / P - 1.0          # return D -> D+1 (the label)
    s = score.where(mask)
    out = {}
    turns = []
    prev_w = pd.Series(0.0, index=P.columns)
    for d in P.index:
        row = s.loc[d].dropna()
        if len(row) < 50:
            out[d] = 0.0
            continue
        q_hi = row.quantile(1 - top_frac)
        longs = row[row >= q_hi].index
        w = pd.Series(0.0, index=P.columns)
        if style == "long":
            if len(longs):
                w[longs] = 1.0 / len(longs)       # fully-invested long, absolute return
        elif style == "excess":
            if len(longs):
                w[longs] = 1.0 / len(longs)
            uni = row.index
            w[uni] -= 1.0 / len(uni)              # long top vs equal-weight market
        else:  # ls
            q_lo = row.quantile(top_frac)
            shorts = row[row <= q_lo].index
            if len(longs):
                w[longs] = 0.5 / len(longs)
            if len(shorts):
                w[shorts] = -0.5 / len(shorts)
        r = (w * fwd.loc[d].fillna(0)).sum()
        turnover = (w - prev_w).abs().sum()
        out[d] = r - turnover * cost_bps * 1e-4
        turns.append(turnover)
        prev_w = w
    return pd.Series(out).sort_index(), float(np.mean(turns)) if turns else 0.0


def benchmark_universe(P: pd.DataFrame, mask: pd.DataFrame) -> pd.Series:
    """Equal-weight return of the tradable universe each month (market proxy)."""
    fwd = P.shift(-1) / P - 1.0
    out = {}
    for d in P.index:
        names = mask.loc[d][mask.loc[d]].index
        f = fwd.loc[d, names].dropna()
        out[d] = f.mean() if len(f) else 0.0
    return pd.Series(out).sort_index()


# ---------------------------------------------------------------- metrics
def metrics(m: pd.Series) -> dict:
    d = m.dropna()
    n = len(d)
    if n < 12:
        return dict(n=n, sharpe=0, ann=0, t=0, dd=0, hit=0)
    mean, sd = d.mean(), d.std(ddof=1)
    sharpe = mean / sd * np.sqrt(TRADING_MONTHS) if sd > 0 else 0
    eq = (1 + d).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    t = mean / (sd / np.sqrt(n)) if sd > 0 else 0
    return dict(n=n, sharpe=sharpe, ann=mean * TRADING_MONTHS, t=t, dd=dd,
                hit=(d > 0).mean() * 100)


def dsr(m: pd.Series, n_trials: int) -> float:
    d = m.dropna()
    if len(d) < 24 or d.std() == 0:
        return float("nan")
    sr = d.mean() / d.std(ddof=1)
    g3, g4 = skew(d), kurtosis(d, fisher=False)
    sd_sr = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr**2) / (len(d) - 1))
    e = 0.5772156649
    emax = sd_sr * ((1 - e) * norm.ppf(1 - 1.0 / n_trials) +
                    e * norm.ppf(1 - 1.0 / (n_trials * np.e)))
    return float(norm.cdf((sr - emax) / sd_sr))


def line(name, m):
    return (f"  {name:<10} n={m['n']:<4} Sharpe={m['sharpe']:>6.2f}  "
            f"ann={m['ann']*100:>6.1f}%  t={m['t']:>5.2f}  "
            f"maxDD={m['dd']*100:>6.1f}%  hit={m['hit']:>4.1f}%")


def main(oos_frac: float = 0.35, mcap_floor: float = MIN_MARKETCAP):
    print(f"loading Sharadar cache ... (marketcap floor ${mcap_floor/1e9:.1f}B)")
    tk, sep, sf1 = load()
    P = price_panel(sep)
    print(f"price panel: {P.shape[0]} month-ends x {P.shape[1]} tickers "
          f"({P.index.min().date()} -> {P.index.max().date()})")
    fund = pit_fundamentals(
        sep[["date", "ticker"]].drop_duplicates(), sf1)
    print(f"PIT fundamentals rows: {len(fund):,}")

    # tradable mask: price floor + marketcap floor, PIT
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= MIN_PRICE) & (mcap >= mcap_floor)
    print(f"avg tradable names/month: {mask.sum(axis=1).mean():.0f}")

    factors = compute_factors(P, fund)
    split = P.index[int(len(P) * (1 - oos_frac))]
    n_trials = len(factors)
    print(f"\nOOS split = {split.date()}   cost={COST_BPS_ONEWAY}bp/side   N_trials={n_trials}")

    print("\n--- DECILE LONG-SHORT (top vs bottom decile) ---")
    for name, sc in factors.items():
        r, to = backtest_factor(P, sc, mask)
        oos = metrics(r[r.index >= split])
        p = dsr(r, n_trials)
        print(line(name, metrics(r)) + f"  turn={to:.2f}")
        print(line("  OOS", oos) + f"  DSR={p:.3f}" + ("  PASS" if p > 0.95 else "  fail"))

    print("\n--- LONG-ONLY top decile vs universe (deployable, no microcap short) ---")
    lo = {}
    for name, sc in factors.items():
        r, to = backtest_factor(P, sc, mask, long_only=True)
        lo[name] = r
        oos = metrics(r[r.index >= split])
        p = dsr(r, n_trials)
        print(line(name, metrics(r)) + f"  turn={to:.2f}")
        print(line("  OOS", oos) + f"  DSR={p:.3f}" + ("  PASS" if p > 0.95 else "  fail"))

    print("\n--- YEARLY Sharpe (is the OOS edge persistent or concentrated?) ---")
    for name in ["momentum", "composite3"]:
        for tag, r in [("L/S", backtest_factor(P, factors[name], mask)[0]),
                       ("LO ", lo[name])]:
            by = r.groupby(r.index.year).apply(
                lambda x: x.mean() / x.std() * np.sqrt(12) if x.std() > 0 else 0.0)
            cells = "  ".join(f"{y}:{v:>5.1f}" for y, v in by.items() if y >= 2014)
            print(f"  {name:<9} {tag}  {cells}")

    # ---- SECTOR-NEUTRAL test: is the edge real alpha or just a sector bet? ----
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    print(f"\n--- SECTOR-NEUTRAL (demean within sicsector; {sector.nunique()} sectors) ---")
    print("    is composite/momentum real alpha or a long-tech bet?")
    for name in ["momentum", "composite3"]:
        sn = sector_neutralize(factors[name], sector)
        for tag, kw in [("L/S", {}), ("LO ", {"long_only": True})]:
            r, to = backtest_factor(P, sn, mask, **kw)
            full = metrics(r); oos = metrics(r[r.index >= split]); p = dsr(r, n_trials)
            print(line(f"{name} {tag}", full) + f" turn={to:.2f}")
            print(line("  OOS", oos) + f"  DSR={p:.3f}" + ("  PASS" if p > 0.95 else "  fail"))
        # yearly for the neutralized L/S
        rls, _ = backtest_factor(P, sn, mask)
        by = rls.groupby(rls.index.year).apply(
            lambda x: x.mean() / x.std() * np.sqrt(12) if x.std() > 0 else 0.0)
        cells = "  ".join(f"{y}:{v:>5.1f}" for y, v in by.items() if y >= 2018)
        print(f"  {name:<9} SN-yearly  {cells}")


def _block_bootstrap_sharpe(r: pd.Series, block: int = 6, n: int = 2000) -> tuple:
    """Stationary block bootstrap CI for annualized Sharpe (handles autocorrelation)."""
    d = r.dropna().values
    L = len(d)
    if L < 24:
        return (np.nan, np.nan, np.nan)
    rng = np.random.RandomState(12345)
    sh = []
    nblocks = int(np.ceil(L / block))
    for _ in range(n):
        starts = rng.randint(0, L, nblocks)
        idx = np.concatenate([np.arange(s, s + block) % L for s in starts])[:L]
        x = d[idx]
        sd = x.std(ddof=1)
        sh.append(x.mean() / sd * np.sqrt(12) if sd > 0 else 0.0)
    sh = np.array(sh)
    return (np.percentile(sh, 5), np.percentile(sh, 50), np.percentile(sh, 95))


def _cagr(r: pd.Series) -> float:
    d = r.dropna()
    if len(d) < 12:
        return 0.0
    return (1 + d).prod() ** (12 / len(d)) - 1


def spec(mcap_floor: float = 2e9, oos_frac: float = 0.35, target_vol: float = 0.10):
    """Point-1 deliverable: ABSOLUTE deployable performance of the champion +
    benchmark + vol-target, for the operational spec."""
    print(f"loading cache (floor ${mcap_floor/1e9:.1f}B) ...")
    tk, sep, sf1 = load()
    P = price_panel(sep)
    fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= MIN_PRICE) & (mcap >= mcap_floor)
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    facs = compute_factors(P, fund, mom_lb=12)
    sn = sector_neutralize(facs["composite3"], sector)
    split = P.index[int(len(P) * (1 - oos_frac))]

    longr, to = backtest_factor(P, sn, mask, style="long", top_frac=0.2)   # quintile
    bench = benchmark_universe(P, mask)
    excess = (longr - bench).dropna()
    avg_names = int(mask.sum(axis=1).mean() * 0.2)

    print(f"\n=== CHAMPION OPERATIONAL SPEC ===")
    print(f"universe >${mcap_floor/1e9:.0f}B liquid US equities (~{int(mask.sum(axis=1).mean())} names/mo)")
    print(f"long top quintile by sector-neutral composite (~{avg_names} positions), "
          f"equal-weight, monthly, turnover {to:.2f}/mo, cost {COST_BPS_ONEWAY}bp/side\n")

    def report(name, r):
        for tag, seg in [("FULL", r), ("OOS ", r[r.index >= split])]:
            m = metrics(seg)
            print(f"  {name:<16} {tag}  CAGR={_cagr(seg)*100:>5.1f}%  Sharpe={m['sharpe']:>5.2f}  "
                  f"maxDD={m['dd']*100:>6.1f}%  hit={m['hit']:>4.1f}%")

    report("strategy (long)", longr)
    report("benchmark (univ)", bench)
    report("excess (alpha)", excess)

    # vol-target overlay (leak-safe: scale by target / trailing realized vol)
    tv = longr.rolling(12, min_periods=6).std().shift(1) * np.sqrt(12)
    lev = (target_vol / tv).clip(upper=1.5).fillna(1.0)
    vt = (lev * longr).dropna()
    print()
    report(f"vol-target {int(target_vol*100)}%", vt)

    print("\n  Bootstrap OOS Sharpe CI (strategy long, block=6):")
    lo5, med, hi95 = _block_bootstrap_sharpe(longr[longr.index >= split])
    print(f"    90% CI = [{lo5:.2f}, {hi95:.2f}]  median={med:.2f}")


def book(mcap_floor: float = 2e9, oos_frac: float = 0.35):
    """Build the 3-leg LONG-ONLY book (momentum + value + gross_profit), measure the
    OOS cross-correlation, and the combined Sharpe. The synthesis prize: diversify the
    validated momentum composite, don't hunt one more standalone factor."""
    tk, sep, sf1 = load()
    P = price_panel(sep)
    fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= MIN_PRICE) & (mcap >= mcap_floor)
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    facs = compute_factors(P, fund, mom_lb=12)
    split = P.index[int(len(P) * (1 - oos_frac))]

    legs = {"momentum": facs["momentum"], "value": facs["value"],
            "gross_profit": facs["gross_profit"], "composite3": facs["composite3"]}
    rets = {}
    print(f"OOS split={split.date()}  legs = long-only quintile, sector-neutral, excess vs EW mkt\n")
    print("STANDALONE legs:")
    for nm, sc in legs.items():
        sn = sector_neutralize(sc, sector)
        r, _ = backtest_factor(P, sn, mask, style="excess", top_frac=0.2)
        rets[nm] = r
        o = metrics(r[r.index >= split])
        print(line(nm, metrics(r)) + " | " + f"OOS Sh={o['sharpe']:.2f} t={o['t']:.2f} DSR={dsr(r,4):.3f}")

    R = pd.DataFrame(rets)
    Roos = R[R.index >= split]
    print("\nOOS correlation (momentum/value/gross_profit):")
    print(Roos[["momentum", "value", "gross_profit"]].corr().round(2).to_string())

    # combined 3-leg books (exclude composite3 which already contains momentum+value)
    three = R[["momentum", "value", "gross_profit"]]
    # equal-weight
    ew = three.mean(axis=1)
    # inverse-vol risk parity, weights from IS only (leak-safe)
    isvol = three[three.index < split].std()
    w = (1 / isvol) / (1 / isvol).sum()
    rp = (three * w).sum(axis=1)
    print(f"\n  IS inverse-vol weights: {w.round(2).to_dict()}")
    for nm, r in [("3-leg equal-wt", ew), ("3-leg risk-parity", rp),
                  ("momentum-only", R["momentum"]), ("composite3", R["composite3"])]:
        o = metrics(r[r.index >= split])
        lo5, _, hi = _block_bootstrap_sharpe(r[r.index >= split])
        print(line(nm, metrics(r)) + f" | OOS Sh={o['sharpe']:.2f} t={o['t']:.2f} "
              f"maxDD={o['dd']*100:.1f}% DSR={dsr(r,4):.3f} CI=[{lo5:.2f},{hi:.2f}]")


def robust(mcap_floor: float = 2e9, oos_frac: float = 0.35):
    """Robustness battery on the champion: sector-neutral COMPOSITE long-only."""
    print(f"loading cache (floor ${mcap_floor/1e9:.1f}B) ...")
    tk, sep, sf1 = load()
    P = price_panel(sep)
    fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= MIN_PRICE) & (mcap >= mcap_floor)
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    split = P.index[int(len(P) * (1 - oos_frac))]
    print(f"OOS split={split.date()}  champion=composite long-only sector-neutral\n")

    def champ(mom_lb=12, top_frac=0.1, cost=COST_BPS_ONEWAY):
        facs = compute_factors(P, fund, mom_lb=mom_lb)
        sn = sector_neutralize(facs["composite3"], sector)
        r, to = backtest_factor(P, sn, mask, cost_bps=cost, long_only=True, top_frac=top_frac)
        return r, to

    print("A) MOMENTUM LOOKBACK (months):")
    for lb in [3, 6, 9, 12]:
        r, _ = champ(mom_lb=lb)
        o = metrics(r[r.index >= split])
        print(f"   lb={lb:>2}  OOS Sharpe={o['sharpe']:>5.2f} t={o['t']:>5.2f} "
              f"ann={o['ann']*100:>5.1f}% maxDD={o['dd']*100:>6.1f}%")

    print("\nB) PORTFOLIO CUT (top fraction):")
    for tf, nm in [(0.05, "top5%"), (0.1, "decile"), (0.2, "quintile"), (0.33, "tercile")]:
        r, to = champ(top_frac=tf)
        o = metrics(r[r.index >= split])
        print(f"   {nm:<8} OOS Sharpe={o['sharpe']:>5.2f} t={o['t']:>5.2f} "
              f"maxDD={o['dd']*100:>6.1f}% turn={to:.2f}")

    print("\nC) COST SENSITIVITY (bps/side):")
    for c in [5, 10, 20, 30, 50]:
        r, _ = champ(cost=c)
        o = metrics(r[r.index >= split])
        print(f"   {c:>2}bp  OOS Sharpe={o['sharpe']:>5.2f} t={o['t']:>5.2f} ann={o['ann']*100:>5.1f}%")

    print("\nD) SUB-PERIOD STABILITY (champion decile 12m):")
    r, _ = champ()
    for lo_, hi_, lab in [("2016-10", "2021-06", "2016-21"), ("2021-06", "2026-12", "2021-26")]:
        seg = r[(r.index >= lo_) & (r.index < hi_)]
        m = metrics(seg)
        print(f"   {lab}  Sharpe={m['sharpe']:>5.2f} t={m['t']:>5.2f} ann={m['ann']*100:>5.1f}% n={m['n']}")

    print("\nE) BLOCK-BOOTSTRAP OOS Sharpe CI (champion, 2000 resamples, block=6):")
    r, _ = champ()
    oos = r[r.index >= split]
    lo5, med, hi95 = _block_bootstrap_sharpe(oos)
    print(f"   OOS Sharpe 90% CI = [{lo5:.2f}, {hi95:.2f}]  median={med:.2f}  "
          f"{'ROBUST >0' if lo5 > 0 else 'CI includes 0'}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "robust":
        robust()
    elif len(sys.argv) > 1 and sys.argv[1] == "spec":
        spec()
    elif len(sys.argv) > 1 and sys.argv[1] == "book":
        book()
    else:
        floor = float(sys.argv[1]) * 1e9 if len(sys.argv) > 1 else MIN_MARKETCAP
        main(mcap_floor=floor)
