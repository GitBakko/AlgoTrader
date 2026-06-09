"""Probe: which WIDER ORB candidates are tradeable on Capital.com demo?

Read-only market-data (GET /markets/{epic}) on the experiment session — prunes
the widened ORB universe to confirmed-tradeable epics so the live loop doesn't
waste a GET + 429 budget on missing names every pass. Run from backend/.
Prints a Python-ready TRADEABLE list to paste into forward_lab.ORB_UNIVERSE.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from forward_lab import _connected_client  # noqa: E402

# Candidate pool = live-30 + liquid US large/mid-caps (semis, fintech, banks,
# pharma, industrials, energy, consumer). SQ dropped (delisted on data feeds).
CANDIDATES = sorted({
    "AAPL", "NVDA", "TSLA", "MSFT", "AMD", "AMZN", "META", "GOOGL", "NFLX", "AVGO",
    "JPM", "V", "MA", "UNH", "XOM", "JNJ", "WMT", "PG", "HD", "COST",
    "DIS", "BAC", "KO", "PEP", "CSCO", "ORCL", "CRM", "ADBE", "PFE", "INTC",
    "QCOM", "TXN", "AMAT", "MU", "LRCX", "ADI", "NXPI", "MRVL", "KLAC", "SNPS",
    "PYPL", "SHOP", "UBER", "ABNB", "COIN", "PLTR", "SNOW", "NOW", "PANW",
    "BKNG", "GS", "MS", "C", "WFC", "AXP", "SCHW", "BLK", "SPGI", "CB",
    "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY", "AMGN", "GILD", "CVS",
    "CAT", "DE", "BA", "GE", "HON", "UPS", "LMT", "RTX", "MMM", "EMR",
    "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "WMB", "OXY", "VLO", "KMI",
    "TGT", "LOW", "NKE", "SBUX", "MCD", "CMG", "MAR", "GM", "F",
})


async def main() -> None:
    client = await _connected_client(experiment=True)
    tradeable, missing = [], []
    try:
        for sym in CANDIDATES:
            try:
                d = await client.get_market_details(sym)
                snap = (d or {}).get("snapshot") or {}
                status = (d or {}).get("snapshot", {}).get("marketStatus") or (
                    (d or {}).get("instrument", {}) or {}).get("name", "")
                if snap.get("bid") is not None or snap.get("offer") is not None:
                    tradeable.append(sym)
                else:
                    missing.append((sym, "no snapshot bid/offer"))
            except Exception as e:  # noqa: BLE001
                missing.append((sym, str(e)[:60]))
            await asyncio.sleep(0.12)   # 429 pacing
    finally:
        await client.close()
    print(f"\n===== TRADEABLE {len(tradeable)}/{len(CANDIDATES)} =====")
    # print as a paste-ready python list, 10 per line
    for i in range(0, len(tradeable), 10):
        print("    " + ", ".join(f'"{s}"' for s in tradeable[i:i + 10]) + ",")
    print(f"\n===== MISSING {len(missing)} =====")
    for sym, why in missing:
        print(f"  {sym}: {why}")


if __name__ == "__main__":
    asyncio.run(main())
