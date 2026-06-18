"""Forward Demo Lab CLI. Run from backend/.

Subcommands:
  discover-account     print the accountId of the "Account Demo" experiment account
  validate-isolation   PROVE the experiment session's active account is independent
                       of the soak session BEFORE any live order (Task 11 gate)
  dry-run              one session-open pass, log intended gap-fade orders (no orders sent)
  run                  live: schedule session-open + mark passes (APScheduler)
  mark                 one mark/close pass now
  status               print the ledger
  score                print the kill/promote verdict
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from loguru import logger  # noqa: E402

from src.broker.client import CapitalComClient  # noqa: E402
from src.utils.config import get_settings  # noqa: E402
from forward.executor import ExperimentExecutor  # noqa: E402
from forward.ledger import ForwardLedger  # noqa: E402
from forward.scheduler import ExperimentScheduler  # noqa: E402
from forward.scorer import score  # noqa: E402

EXPERIMENT_ACCOUNT_NAME = "Account Demo"
LEDGER_PATH = ROOT / "data" / "forward_lab" / "ledger.db"
UNIVERSE = ["AAPL", "NVDA", "TSLA", "MSFT", "AMD"]  # liquid US stock CFDs (real gaps)
ORB_UNIVERSE = [
    # 97 Capital.com-demo-tradeable US large/mid-caps (probe_epic_availability.py
    # 2026-06-09: 97/98, only EMR not-found). Wider pool keeps >=5 RVOL>=1.5 names
    # eligible every day (probe_orb_ratecheck: eligible/day 2.98 @30 -> 4.95 @99,
    # N=100 ~8wk -> ~5wk). Non-eligible names cost no broker GET (eligibility-gated
    # before any per-epic fetch). skip-graceful on any epic/data miss.
    "AAPL", "ABBV", "ABNB", "ABT", "ADBE", "ADI", "AMAT", "AMD", "AMGN", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BKNG", "BLK", "BMY", "C", "CAT", "CB",
    "CMG", "COIN", "COP", "COST", "CRM", "CSCO", "CVS", "CVX", "DE", "DHR",
    "DIS", "EOG", "F", "GE", "GILD", "GM", "GOOGL", "GS", "HD", "HON",
    "INTC", "JNJ", "JPM", "KLAC", "KMI", "KO", "LLY", "LMT", "LOW", "LRCX",
    "MA", "MAR", "MCD", "META", "MMM", "MPC", "MRK", "MRVL", "MS", "MSFT",
    "MU", "NFLX", "NKE", "NOW", "NVDA", "NXPI", "ORCL", "OXY", "PANW", "PEP",
    "PFE", "PG", "PLTR", "PSX", "PYPL", "QCOM", "RTX", "SBUX", "SCHW", "SHOP",
    "SLB", "SNOW", "SNPS", "SPGI", "TGT", "TMO", "TSLA", "TXN", "UBER", "UNH",
    "UPS", "V", "VLO", "WFC", "WMB", "WMT", "XOM",
]


async def discover_account(client, name: str = EXPERIMENT_ACCOUNT_NAME) -> str | None:
    for a in await client.get_accounts():
        if a.account_name == name:
            return a.account_id
    return None


def _strategies() -> list:
    from forward.strategy import GapFadeStrategy, ORBStrategy
    s = get_settings()
    return [
        GapFadeStrategy(epics=UNIVERSE, gap_threshold=s.forward_lab_gap_threshold),
        ORBStrategy(epics=ORB_UNIVERSE, rvol_min=s.forward_lab_orb_rvol_min,
                    breakout_buffer=s.forward_lab_orb_breakout_buffer,
                    stop_atr_mult=s.forward_lab_orb_stop_atr_mult),
    ]


def _screener():
    from forward.screener import RvolScreener
    s = get_settings()
    return RvolScreener(rvol_min=s.forward_lab_orb_rvol_min, top_k=s.forward_lab_orb_top_k,
                        or_window_min=s.forward_lab_orb_or_window_min)


def _yf_ref_close(epic: str) -> float | None:
    """Independent daily-close reference for the executor price-sanity gate (yfinance).
    US-stock epics map 1:1 to yfinance tickers. Graceful: returns None on any failure,
    which leaves the gate inert (never blocks an entry on a reference-lookup hiccup)."""
    try:
        import yfinance as yf

        d = yf.download(epic, period="5d", interval="1d", progress=False, auto_adjust=False)["Close"]
        ser = d[d.columns[0]] if hasattr(d, "columns") else d
        ser = ser.dropna()
        return float(ser.iloc[-1]) if len(ser) else None
    except Exception:  # noqa: BLE001 — sanity reference is best-effort; never raise into the loop
        return None


def _build_scheduler(client, executor):
    s = get_settings()
    return ExperimentScheduler(
        client=client, executor=executor, strategies=_strategies(),
        eod_flatten_et=s.forward_lab_eod_flatten_et, screener=_screener(),
        or_window_min=s.forward_lab_orb_or_window_min,
        session_open_et=s.forward_lab_session_open_et,
        watch_end_et=s.forward_lab_orb_watch_end_et,
        scan_pacing_s=s.forward_lab_scan_pacing_s,
        ref_price_fetch=_yf_ref_close)


async def _connected_client(experiment: bool = False) -> CapitalComClient:
    """Connected client. experiment=True uses the dedicated experiment API key
    (separate session/CST from the soak); else the default soak creds."""
    s = get_settings()
    if experiment and s.capital_experiment_api_key:
        client = CapitalComClient(api_key=s.capital_experiment_api_key,
                                  email=s.capital_experiment_email,
                                  password=s.capital_experiment_password)
    else:
        client = CapitalComClient()  # demo creds from settings (use_demo=True)
    await client.connect()
    return client


async def _ensure_account(client, account_id: str | None) -> None:
    """Switch the client to account_id only if not already active (Capital.com
    rejects switching to the already-active account: error.not-different.accountId)."""
    if account_id and await client.get_active_account_id() != account_id:
        await client.switch_account(account_id)


async def cmd_discover() -> None:
    client = await _connected_client(experiment=True)
    try:
        accts = await client.get_accounts()
        active = await client.get_active_account_id()
        print("Accounts visible to the experiment API key:")
        for a in accts:
            mark = "  <- ACTIVE" if a.account_id == active else ""
            print(f"  id={a.account_id}  name={a.account_name!r}  bal={a.balance}{mark}")
        print("Set CAPITAL_EXPERIMENT_ACCOUNT_ID to the idle account's id "
              "(the one WITHOUT the soak's positions).")
    finally:
        await client.close()


async def cmd_validate_isolation() -> None:
    """Task 11 gate: prove switching the experiment session does NOT move the
    soak session's active account. Uses TWO independent clients (two CSTs)."""
    s = get_settings()
    exp_id = s.capital_experiment_account_id
    assert exp_id, "set CAPITAL_EXPERIMENT_ACCOUNT_ID first (run discover-account)"
    soak = await _connected_client()
    exp = await _connected_client(experiment=True)
    try:
        soak_before = await soak.get_active_account_id()
        await exp.switch_account(exp_id)
        exp_active = await exp.get_active_account_id()
        soak_after = await soak.get_active_account_id()
        ok = (exp_active == exp_id) and (soak_after == soak_before)
        print(f"soak active before={soak_before} after={soak_after}; "
              f"exp active={exp_active}; ISOLATION {'OK' if ok else 'FAILED'}")
        if not ok:
            print("!!! DO NOT GO LIVE — switching the experiment session moved the "
                  "soak account. Use a SEPARATE LOGIN for the experiment instead.")
    finally:
        await soak.close()
        await exp.close()


def _make_executor(client, dry_run: bool) -> ExperimentExecutor:
    s = get_settings()
    return ExperimentExecutor(
        client=client, experiment_account_id=s.capital_experiment_account_id or "",
        ledger=ForwardLedger(LEDGER_PATH), notional_usd=s.forward_lab_notional_usd,
        max_concurrent=s.forward_lab_max_concurrent,
        daily_loss_limit_eur=s.forward_lab_daily_loss_limit_usd, dry_run=dry_run)


async def cmd_dry_run() -> None:
    client = await _connected_client(experiment=True)
    try:
        ex = _make_executor(client, dry_run=True)
        sched = _build_scheduler(client, ex)
        await sched.entry_pass()
    finally:
        await client.close()


async def cmd_mark() -> None:
    s = get_settings()
    client = await _connected_client(experiment=True)
    try:
        await _ensure_account(client, s.capital_experiment_account_id)
        ex = _make_executor(client, dry_run=False)
        sched = _build_scheduler(client, ex)
        await sched.mark_pass()
    finally:
        await client.close()


async def cmd_live_open() -> None:
    """LIVE: run one entry_pass (gap-fade + ORB) on the experiment account (switches
    to it first; the executor's isolation guard re-checks before every order)."""
    s = get_settings()
    client = await _connected_client(experiment=True)
    try:
        await _ensure_account(client, s.capital_experiment_account_id)
        ex = _make_executor(client, dry_run=False)
        sched = _build_scheduler(client, ex)
        await sched.entry_pass()
    finally:
        await client.close()


async def cmd_run() -> None:
    """Persistent autonomous loop: entry_pass every 5 min
    (09:30-12:00 ET window (13:30-16:00 UTC summer / 14:30-17:00 UTC winter))
    + mark/exit management every 15 min + EOD flatten.
    Launch once, detached (like the backend). Ctrl-C to stop.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    s = get_settings()
    client = await _connected_client(experiment=True)
    await client.switch_account(s.capital_experiment_account_id)
    ex = _make_executor(client, dry_run=False)
    sched = _build_scheduler(client, ex)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(sched.entry_pass, IntervalTrigger(minutes=5),
                      id="entry_pass", misfire_grace_time=120)
    scheduler.add_job(sched.mark_pass, IntervalTrigger(minutes=15), id="mark")
    scheduler.start()
    logger.success("[forward-lab] RUN loop started — entry_pass every 5min "
                   "(09:30-12:00 ET window (13:30-16:00 UTC summer / 14:30-17:00 UTC winter)), "
                   "mark every 15min, EOD flatten. Ctrl-C to stop.")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[forward-lab] RUN loop stopping...")
    finally:
        scheduler.shutdown(wait=False)
        await client.close()


def cmd_status() -> None:
    led = ForwardLedger(LEDGER_PATH)
    print("OPEN:", led.list_open())
    for name in ("gap_fade", "orb"):
        print(f"REALIZED[{name}]:", led.realized(name))


def cmd_score() -> None:
    led = ForwardLedger(LEDGER_PATH)
    for name in ("gap_fade", "orb"):
        print(f"[{name}]", score(led.realized(name)))


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "discover-account":
        asyncio.run(cmd_discover())
    elif cmd == "validate-isolation":
        asyncio.run(cmd_validate_isolation())
    elif cmd == "dry-run":
        asyncio.run(cmd_dry_run())
    elif cmd == "mark":
        asyncio.run(cmd_mark())
    elif cmd == "live-open":
        asyncio.run(cmd_live_open())
    elif cmd == "run":
        asyncio.run(cmd_run())
    elif cmd == "status":
        cmd_status()
    elif cmd == "score":
        cmd_score()
    else:
        print(f"unknown command {cmd!r} — see module docstring for subcommands")


if __name__ == "__main__":
    main()
