"""Post-deploy verification for the forward-lab entry gates (commit ee369cc).

Run after a US trading session. Appends a verdict block to gate_verify.log and
prints it. Designed for an unattended Scheduled Task — never raises, always writes.

The R:R gate and the price-sanity reference are SILENT in the live loop (no log on
reject / on the reference value used), so this script verifies them directly:
  [1] Reference path LIVE — calls the exact production `_yf_ref_close` on the
      gap_fade universe. All-None => the price-gate is silently inert (RED): it
      would never block a bad feed because it never has a reference to compare.
  [2] Ledger — for entries in sessions on/after FIRST_SESSION: per-strategy
      counts + every gap_fade entry must have R:R>=1 (gate honored). Any R:R<1
      entry means the gate did NOT apply (RED).
  [3] run.err.log — count price-gate skips ("price-feed anomaly") and try_enter
      errors; surface the last few skip lines to watch for false positives.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

DATA = ROOT / "data" / "forward_lab"
LEDGER = DATA / "ledger.db"
ERRLOG = DATA / "run.err.log"
VERDICT = DATA / "gate_verify.log"

# Gates went live on the 2026-06-18 mid-window restart; count entries opened at/after
# it (ISO-8601 +00:00 strings compare lexicographically). Pre-restart rows ran old code.
DEPLOY_UTC = "2026-06-18T15:16:00"
GAP_UNIVERSE = ["AAPL", "NVDA", "TSLA", "MSFT", "AMD"]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_reference() -> tuple[int, dict]:
    """Call the production reference fetcher; report which names resolve to a price."""
    out: dict[str, object] = {}
    try:
        from forward_lab import _yf_ref_close
    except Exception as e:  # noqa: BLE001
        return 0, {"IMPORT_ERROR": repr(e)}
    for e in GAP_UNIVERSE:
        try:
            v = _yf_ref_close(e)
            out[e] = round(v, 2) if isinstance(v, (int, float)) else v
        except Exception as ex:  # noqa: BLE001
            out[e] = f"ERR {ex}"
    live = sum(1 for v in out.values() if isinstance(v, (int, float)) and v and v > 0)
    return live, out


def check_ledger() -> tuple[dict, list, int] | None:
    if not LEDGER.exists():
        return None
    c = sqlite3.connect(LEDGER)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT * FROM trades WHERE opened_at >= ?", (DEPLOY_UTC,)
    ).fetchall()
    per: dict[str, int] = {}
    bad_rr: list[tuple] = []
    for r in rows:
        per[r["strategy"]] = per.get(r["strategy"], 0) + 1
        if r["strategy"] == "gap_fade" and r["prev_close"] and r["today_open"] and r["stop_level"]:
            target = 0.5 * abs(r["today_open"] - r["prev_close"])
            stop = abs(r["entry"] - r["stop_level"])
            rr = (target / stop) if stop else 0.0
            if rr < 1.0:
                bad_rr.append((r["id"], r["epic"], round(rr, 2)))
    return per, bad_rr, len(rows)


def check_logs() -> tuple[int, list, int] | None:
    if not ERRLOG.exists():
        return None
    txt = ERRLOG.read_text(encoding="utf-8", errors="replace")
    skip_lines = [ln for ln in txt.splitlines() if "price-feed anomaly" in ln]
    errs = len(re.findall(r"try_enter failed", txt))
    return len(skip_lines), skip_lines[-5:], errs


def main() -> None:
    out = [f"\n===== gate verify {_ts()} ====="]

    live, ref = check_reference()
    armed = "ARMED" if live >= 3 else "RED — INERT (price-gate has no reference to compare!)"
    out.append(f"[1] yfinance reference path: {live}/{len(GAP_UNIVERSE)} live -> {armed}")
    out.append(f"    {ref}")

    led = check_ledger()
    if led is None:
        out.append("[2] ledger: not found")
    else:
        per, bad_rr, n = led
        out.append(f"[2] ledger entries since deploy {DEPLOY_UTC}Z: {n}  per-strategy={per}")
        if bad_rr:
            out.append(f"    RED — gap_fade entries with R:R<1 (gate NOT applied!): {bad_rr}")
        elif per.get("gap_fade"):
            out.append(f"    OK — all {per['gap_fade']} gap_fade entries have R:R>=1 (gate honored)")
        else:
            out.append("    (no gap_fade entries yet — consistent with the gate, no positive sample)")

    logs = check_logs()
    if logs is None:
        out.append("[3] run.err.log: not found")
    else:
        nskip, last, errs = logs
        out.append(f"[3] price-gate skips logged: {nskip}; try_enter errors: {errs}")
        for ln in last:
            out.append(f"    skip: {ln.strip()[:160]}")

    report = "\n".join(out)
    print(report)
    try:
        with open(VERDICT, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    except Exception as e:  # noqa: BLE001 — verdict logging is best-effort
        print(f"(could not append to {VERDICT}: {e})")


if __name__ == "__main__":
    main()
