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
from forward.strategy import GapFadeStrategy  # noqa: E402

EXPERIMENT_ACCOUNT_NAME = "Account Demo"
LEDGER_PATH = ROOT / "data" / "forward_lab" / "ledger.db"
UNIVERSE = ["AAPL", "NVDA", "TSLA", "MSFT", "AMD"]  # liquid US stock CFDs (real gaps)


async def discover_account(client, name: str = EXPERIMENT_ACCOUNT_NAME) -> str | None:
    for a in await client.get_accounts():
        if a.account_name == name:
            return a.account_id
    return None


def _strategy() -> GapFadeStrategy:
    s = get_settings()
    return GapFadeStrategy(epics=UNIVERSE, gap_threshold=s.forward_lab_gap_threshold)


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
        daily_loss_limit_usd=s.forward_lab_daily_loss_limit_usd, dry_run=dry_run)


async def cmd_dry_run() -> None:
    client = await _connected_client(experiment=True)
    try:
        ex = _make_executor(client, dry_run=True)
        sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                    eod_flatten_utc=get_settings().forward_lab_eod_flatten_utc)
        await sched.on_session_open()
    finally:
        await client.close()


async def cmd_mark() -> None:
    s = get_settings()
    client = await _connected_client(experiment=True)
    try:
        await client.switch_account(s.capital_experiment_account_id)
        ex = _make_executor(client, dry_run=False)
        sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                    eod_flatten_utc=s.forward_lab_eod_flatten_utc)
        await sched.mark_pass()
    finally:
        await client.close()


async def cmd_live_open() -> None:
    """LIVE: place real gap-fade entries on the experiment account (switches to it
    first; the executor's isolation guard re-checks before every order)."""
    s = get_settings()
    client = await _connected_client(experiment=True)
    try:
        await client.switch_account(s.capital_experiment_account_id)
        ex = _make_executor(client, dry_run=False)
        sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                    eod_flatten_utc=s.forward_lab_eod_flatten_utc)
        await sched.on_session_open()
    finally:
        await client.close()


async def cmd_run() -> None:
    """Persistent autonomous loop: gap-fade entries at the US cash open
    (13:30 UTC, Mon-Fri) + mark/exit management every 15 min + EOD flatten.
    Launch once, detached (like the backend). Ctrl-C to stop.

    NOTE: 13:30 UTC = US open in summer (EDT). In winter (EST) the open is
    14:30 UTC — adjust the cron hour then.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    s = get_settings()
    client = await _connected_client(experiment=True)
    await client.switch_account(s.capital_experiment_account_id)
    ex = _make_executor(client, dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                eod_flatten_utc=s.forward_lab_eod_flatten_utc)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(sched.on_session_open,
                      CronTrigger(day_of_week="mon-fri", hour=13, minute=30, timezone="UTC"),
                      id="gap_fade_open", misfire_grace_time=300)
    scheduler.add_job(sched.mark_pass, IntervalTrigger(minutes=15), id="mark")
    scheduler.start()
    logger.success("[forward-lab] RUN loop started — entries 13:30 UTC (Mon-Fri), "
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
    print("REALIZED:", led.realized("gap_fade"))


def cmd_score() -> None:
    led = ForwardLedger(LEDGER_PATH)
    print(score(led.realized("gap_fade")))


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
