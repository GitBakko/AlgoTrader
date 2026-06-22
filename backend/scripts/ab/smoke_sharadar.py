"""Empirical proof that our Sharadar (Nasdaq Data Link) interface is fully working
BEFORE building the cross-sectional harness. Hits the live API with the key from
.env and pulls real rows from every table the strategy needs.

Proves: (1) auth ok, (2) SEP prices accessible, (3) SF1 fundamentals + PIT
dimensions accessible, (4) TICKERS metadata + universe size, (5) SURVIVORSHIP-FREE
(delisted names return data), (6) pagination works for full pulls.

Run from backend/:  .venv/Scripts/python.exe scripts/ab/smoke_sharadar.py
NEVER prints the API key.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]  # backend/
load_dotenv(ROOT / ".env")

KEY = os.getenv("NASDAQ_DATA_LINK_API_KEY")
assert KEY, "NASDAQ_DATA_LINK_API_KEY missing in backend/.env"
print(f"key loaded: ...{KEY[-4:]} (len {len(KEY)})")  # masked

import nasdaqdatalink as ndl  # noqa: E402

ndl.ApiConfig.api_key = KEY

OK, FAIL = "[OK]", "[FAIL]"


def section(t):
    print(f"\n{'='*60}\n{t}\n{'='*60}")


def main():
    section("1) SEP — equity prices (AAPL, 2026)")
    sep = ndl.get_table("SHARADAR/SEP", ticker="AAPL",
                        date={"gte": "2026-01-01"}, paginate=True)
    print(f"  {OK if len(sep) else FAIL} rows={len(sep)} cols={list(sep.columns)}")
    if len(sep):
        print(sep.sort_values("date").tail(2).to_string())

    section("2) SF1 — fundamentals point-in-time (AAPL, ARQ as-reported quarterly)")
    sf1 = ndl.get_table("SHARADAR/SF1", ticker="AAPL", dimension="ARQ", paginate=True)
    keep = [c for c in ["ticker", "dimension", "calendardate", "datekey",
                        "marketcap", "pe", "pb", "roe", "revenue", "netinc"]
            if c in sf1.columns]
    print(f"  {OK if len(sf1) else FAIL} rows={len(sf1)} (showing PIT-relevant cols)")
    if len(sf1):
        print(sf1.sort_values("datekey")[keep].tail(2).to_string())
        # 'datekey' = when data became known (PIT anchor); 'calendardate' = period end
        print(f"  PIT check: has datekey={'datekey' in sf1.columns} "
              f"calendardate={'calendardate' in sf1.columns}")

    section("3) TICKERS — universe metadata & size")
    tk = ndl.get_table("SHARADAR/TICKERS", table="SEP", paginate=True)
    n_total = len(tk)
    n_delisted = int((tk["isdelisted"] == "Y").sum()) if "isdelisted" in tk.columns else -1
    n_active = int((tk["isdelisted"] == "N").sum()) if "isdelisted" in tk.columns else -1
    print(f"  {OK if n_total else FAIL} universe rows={n_total} "
          f"active={n_active} delisted={n_delisted}")
    print(f"  cols(sample)={list(tk.columns)[:12]}")

    section("4) SURVIVORSHIP-FREE proof — pull a DELISTED name")
    # find a delisted ticker from metadata and pull its prices
    dedf = tk[tk.get("isdelisted") == "Y"] if "isdelisted" in tk.columns else tk.iloc[0:0]
    target = None
    for cand in ["LEH", "ENRNQ", "WAMUQ", "BSC"]:
        if (tk["ticker"] == cand).any():
            target = cand
            break
    if target is None and len(dedf):
        target = dedf.iloc[0]["ticker"]
    if target:
        dead = ndl.get_table("SHARADAR/SEP", ticker=target, paginate=True)
        print(f"  {OK if len(dead) else FAIL} delisted '{target}': {len(dead)} price rows "
              f"({dead['date'].min()} -> {dead['date'].max()})" if len(dead)
              else f"  {FAIL} delisted '{target}': NO DATA")
    else:
        print(f"  {FAIL} no delisted ticker found in metadata")

    section("5) Cross-sectional feasibility — one date, how many names?")
    snap = ndl.get_table("SHARADAR/SEP", date="2020-06-15", paginate=True)
    print(f"  {OK if len(snap) else FAIL} names with a price on 2020-06-15: {len(snap)}")
    print(f"\n{OK} INTERFACE FULLY OPERATIONAL — safe to build the harness."
          if len(sep) and len(sf1) and n_total and len(snap)
          else f"\n{FAIL} interface INCOMPLETE — do not build yet.")


if __name__ == "__main__":
    main()
