"""PROBE (gate test): can FREE Binance data give a survivorship-free perp universe?

Survivorship killer #1 can only be solved free if Binance serves history for
DEAD/DELISTED perps. This probe answers three yes/no questions cheaply:

  1. fapi/exchangeInfo  -> how many perps trade TODAY (the biased survivor set).
  2. fapi/fundingRate + klines for KNOWN-DEAD coins (LUNA/FTT/SRM/...) -> does the
     live REST endpoint still return their pre-delisting history?
  3. data.binance.vision S3 listing -> the authoritative list of EVERY UM perp dir
     that ever existed (survivorship-free universe), incl. delisted ones.

If (2) or (3) returns dead-coin history -> survivorship is solvable on free data,
proceed to build the PIT universe. If both are empty -> free data CANNOT solve it,
declare and stop.

Run: .venv/Scripts/python.exe scripts/ab/probe_crypto_universe.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

FAPI = "https://fapi.binance.com/fapi/v1"
VISION = "https://data.binance.vision"

# coins that died or were delisted from Binance USDⓈ-M perps (not in today's survivor set)
DEAD = ["LUNAUSDT", "FTTUSDT", "SRMUSDT", "TOMOUSDT", "ANCUSDT", "COCOSUSDT",
        "RAYUSDT", "BTSUSDT", "SCUSDT", "DGBUSDT", "WAVESUSDT", "CVCUSDT",
        "HNTUSDT", "BTCSTUSDT", "FTMUSDT", "MATICUSDT"]


def _get(url: str, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def probe_live_universe():
    print("=" * 70)
    print("(1) fapi/exchangeInfo — TODAY's trading perps (the biased survivor set)")
    try:
        info = json.loads(_get(f"{FAPI}/exchangeInfo"))
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL {type(e).__name__}: {e}")
        return set()
    perps = [s["symbol"] for s in info["symbols"]
             if s.get("contractType") == "PERPETUAL"
             and s.get("status") == "TRADING"
             and s["symbol"].endswith("USDT")]
    print(f"  live USDT perps trading now: {len(perps)}")
    return set(perps)


def probe_dead_rest():
    print("=" * 70)
    print("(2) fapi REST history for KNOWN-DEAD coins (funding + klines)")
    served = []
    for sym in DEAD:
        nf = nk = 0
        fr_span = kl_span = ""
        try:
            fr = json.loads(_get(
                f"{FAPI}/fundingRate?symbol={sym}&limit=1000&startTime=1546300800000"))
            nf = len(fr)
            if nf:
                import pandas as pd
                t0 = pd.Timestamp(fr[0]["fundingTime"], unit="ms").date()
                t1 = pd.Timestamp(fr[-1]["fundingTime"], unit="ms").date()
                fr_span = f"{t0}->{t1}"
        except Exception as e:  # noqa: BLE001
            fr_span = f"ERR {type(e).__name__}"
        try:
            kl = json.loads(_get(
                f"{FAPI}/klines?symbol={sym}&interval=1d&limit=1500&startTime=0"))
            nk = len(kl)
        except Exception as e:  # noqa: BLE001
            kl_span = f"ERR {type(e).__name__}"
        flag = "SERVED" if (nf or nk) else "empty"
        if nf or nk:
            served.append(sym)
        print(f"  {sym:<10} funding={nf:>4} {fr_span:<24} klines={nk:>4} {kl_span}  [{flag}]")
    return served


def _list_vision(prefix: str) -> list[str]:
    """Enumerate CommonPrefixes (subdir names) under a data.binance.vision prefix."""
    out, marker = [], None
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    while True:
        url = f"{VISION}/?delimiter=/&prefix={prefix}"
        if marker:
            url += f"&marker={marker}"
        xml = _get(url).decode()
        root = ET.fromstring(xml)
        cps = root.findall(f"{ns}CommonPrefixes/{ns}Prefix")
        for cp in cps:
            name = cp.text.rstrip("/").split("/")[-1]
            out.append(name)
        truncated = root.findtext(f"{ns}IsTruncated") == "true"
        if not truncated:
            break
        marker = root.findtext(f"{ns}NextMarker") or (prefix + out[-1] + "/")
    return out


def probe_vision_universe():
    print("=" * 70)
    print("(3) data.binance.vision — EVERY UM perp dir ever (survivorship-free)")
    try:
        klines = _list_vision("data/futures/um/daily/klines/")
        funding = set(_list_vision("data/futures/um/monthly/fundingRate/"))
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL {type(e).__name__}: {e}")
        return set(), set()
    usdt = [s for s in klines if s.endswith("USDT")]
    print(f"  total kline symbol dirs:   {len(klines)}")
    print(f"  USDT perp symbol dirs:     {len(usdt)}")
    print(f"  funding symbol dirs:       {len(funding)}")
    return set(usdt), funding


def main():
    live = probe_live_universe()
    served = probe_dead_rest()
    vis_klines, vis_funding = probe_vision_universe()

    print("=" * 70)
    print("VERDICT")
    if vis_klines:
        dead_in_vision = sorted(vis_klines - live)
        print(f"  survivorship-free USDT universe (vision): {len(vis_klines)} symbols")
        print(f"  of which NOT trading today (delisted/dead): {len(dead_in_vision)}")
        print(f"  funding coverage on those dead names: "
              f"{len([s for s in dead_in_vision if s in vis_funding])}/{len(dead_in_vision)}")
        print(f"  sample dead-but-archived: {dead_in_vision[:25]}")
    if served:
        print(f"  fapi REST also serves dead history for: {served}")
    free_solvable = bool(vis_klines) or bool(served)
    print(f"\n  >>> SURVIVORSHIP SOLVABLE ON FREE DATA: {free_solvable}")
    if free_solvable:
        print("  -> proceed: build PIT universe from the vision listing + dead history.")
    else:
        print("  -> free data cannot give dead coins; survivorship unsolvable free.")


if __name__ == "__main__":
    main()
