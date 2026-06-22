"""Fetch the SURVIVORSHIP-FREE Binance UM perp universe (klines + funding), cached.

Kills survivorship killer #1: instead of today's 30 surviving coins, enumerate EVERY
USDⓈ-M perp that ever traded (from the S3 archive listing) incl. delisted/dead names
(LUNA/FTT/SRM/...), fetch each one's full pre-delisting daily close + funding via fapi
(proven to serve dead history), and cache to parquet. A later analysis builds a
point-in-time universe from this (a coin is tradable on a date iff it has data there).

Non-crypto perps Binance briefly listed (tokenized stocks TSLA/NVDA/..., commodities
XAU/COPPER/NATGAS, ETFs SPY/QQQ/SOXL, index baskets DEFI/FOOTBALL) are EXCLUDED — a
crypto funding strategy must not rank them.

Resumable: skips symbols already cached. Cache dir gitignored.
Run: .venv/Scripts/python.exe scripts/ab/fetch_crypto_perp_universe.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")

FAPI = "https://fapi.binance.com/fapi/v1"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
CACHE = ROOT / "data" / "crypto_perp"
CACHE.mkdir(parents=True, exist_ok=True)
KLINES_PQ = CACHE / "klines_daily.parquet"
FUNDING_PQ = CACHE / "funding_daily.parquet"
DONE_TXT = CACHE / "_done_symbols.txt"

# tokenized stocks / commodities / ETFs / index baskets Binance listed as UM perps —
# NOT crypto, must not enter a crypto funding cross-section.
NON_CRYPTO = {
    # tokenized equities
    "AAPLUSDT", "AMDUSDT", "AMZNUSDT", "AVGOUSDT", "BABAUSDT", "BRKBUSDT", "COINUSDT",
    "COHRUSDT", "CRCLUSDT", "CRWVUSDT", "CSCOUSDT", "DISUSDT", "GOOGLUSDT", "HDUSDT",
    "HOODUSDT", "INTCUSDT", "JPMUSDT", "MRVLUSDT", "MSFTUSDT", "MSTRUSDT", "MUUSDT",
    "NBISUSDT", "NVDAUSDT", "ORCLUSDT", "PLTRUSDT", "QCOMUSDT", "RKLBUSDT", "SNDKUSDT",
    "TSLAUSDT", "TSMUSDT", "UBERUSDT", "WMTUSDT", "METAUSDT", "ARMUSDT", "PAYPUSDT",
    "BIDUSDT", "VUSDT", "OPENAIUSDT", "SPCXUSDT", "NFLXUSDT", "QQQUSDT", "SPYUSDT",
    "EWJUSDT", "EWYUSDT", "SOXLUSDT",
    # commodities / metals / energy
    "XAUUSDT", "XAGUSDT", "XPTUSDT", "XPDUSDT", "COPPERUSDT", "NATGASUSDT", "CLUSDT",
    # index baskets / synthetics
    "DEFIUSDT", "FOOTBALLUSDT", "BLUEBIRDUSDT",
}


def _get(url: str, timeout=30, retries=4):
    for k in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (418, 429):           # rate limited -> back off hard
                time.sleep(2 ** k + 1)
                continue
            if e.code in (400, 404):           # symbol/endpoint not serving -> give up
                return None
            time.sleep(1.0 + k)
        except Exception:                       # noqa: BLE001  transient net
            time.sleep(1.0 + k)
    return None


def enumerate_universe() -> list[str]:
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    out, marker = [], None
    prefix = "data/futures/um/daily/klines/"
    while True:
        url = f"{S3}?delimiter=/&prefix={prefix}"
        if marker:
            url += f"&marker={marker}"
        raw = _get(url)
        r = ET.fromstring(raw.decode())
        for c in r.findall(f"{ns}CommonPrefixes/{ns}Prefix"):
            out.append(c.text.rstrip("/").split("/")[-1])
        if r.findtext(f"{ns}IsTruncated") != "true":
            break
        marker = r.findtext(f"{ns}NextMarker") or (prefix + out[-1] + "/")
    usdt = [s for s in out if s.endswith("USDT") and s not in NON_CRYPTO]
    return sorted(usdt)


def fetch_klines_daily(sym: str) -> pd.DataFrame:
    """Daily close + quote-asset volume (USDT turnover = liquidity proxy, k[7])."""
    rec, start = {}, 0
    while True:
        rows = _get(f"{FAPI}/klines?symbol={sym}&interval=1d&limit=1500&startTime={start}")
        if not rows:
            break
        rows = json.loads(rows)
        if not rows:
            break
        for k in rows:
            dt = pd.Timestamp(k[0], unit="ms").normalize()
            rec[dt] = (float(k[4]), float(k[7]))  # close, quote volume
        if len(rows) < 1500:
            break
        start = rows[-1][0] + 86_400_000
        time.sleep(0.08)
    if not rec:
        return pd.DataFrame(columns=["close", "qvol"])
    df = pd.DataFrame.from_dict(rec, orient="index", columns=["close", "qvol"])
    return df.sort_index()


def fetch_funding_daily(sym: str) -> pd.Series:
    recs, start = [], 1_546_300_800_000  # 2019-01-01
    while True:
        rows = _get(f"{FAPI}/fundingRate?symbol={sym}&limit=1000&startTime={start}")
        if not rows:
            break
        rows = json.loads(rows)
        if not rows:
            break
        for r in rows:
            recs.append((pd.Timestamp(r["fundingTime"], unit="ms").normalize(),
                         float(r["fundingRate"])))
        if len(rows) < 1000:
            break
        start = rows[-1]["fundingTime"] + 1
        time.sleep(0.08)
    if not recs:
        return pd.Series(dtype=float)
    return pd.DataFrame(recs, columns=["date", "f"]).groupby("date")["f"].sum().sort_index()


def load_done() -> set[str]:
    if DONE_TXT.exists():
        return set(DONE_TXT.read_text().split())
    return set()


def append_parquet(path: Path, df_new: pd.DataFrame):
    if path.exists():
        old = pd.read_parquet(path)
        df_new = pd.concat([old, df_new], ignore_index=True)
    df_new.to_parquet(path, index=False)


def main():
    print("Enumerating survivorship-free UM perp universe from S3 archive...")
    universe = enumerate_universe()
    done = load_done()
    todo = [s for s in universe if s not in done]
    print(f"  crypto USDT perps ever traded: {len(universe)}  "
          f"(cached {len(done)}, to fetch {len(todo)})")

    kbuf, fbuf, newly = [], [], []
    t0 = time.time()
    for i, sym in enumerate(todo, 1):
        p = fetch_klines_daily(sym)
        f = fetch_funding_daily(sym)
        n = min(len(p), len(f))
        if n >= 30:
            kbuf.append(pd.DataFrame({"symbol": sym, "date": p.index,
                                      "close": p["close"].values, "qvol": p["qvol"].values}))
            fbuf.append(pd.DataFrame({"symbol": sym, "date": f.index, "funding": f.values}))
        newly.append(sym)
        if i % 25 == 0 or i == len(todo):
            if kbuf:
                append_parquet(KLINES_PQ, pd.concat(kbuf, ignore_index=True))
                append_parquet(FUNDING_PQ, pd.concat(fbuf, ignore_index=True))
                kbuf, fbuf = [], []
            with DONE_TXT.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(newly) + "\n")
            newly = []
            el = time.time() - t0
            print(f"  [{i:>3}/{len(todo)}] {sym:<14} kept-batch flushed  "
                  f"elapsed {el:>5.0f}s  eta {el/i*(len(todo)-i):>5.0f}s")
    print("DONE. cache:")
    if KLINES_PQ.exists():
        k = pd.read_parquet(KLINES_PQ)
        f = pd.read_parquet(FUNDING_PQ)
        print(f"  klines  rows={len(k):>7}  symbols={k.symbol.nunique()}  "
              f"{k.date.min().date()}->{k.date.max().date()}")
        print(f"  funding rows={len(f):>7}  symbols={f.symbol.nunique()}")


if __name__ == "__main__":
    main()
