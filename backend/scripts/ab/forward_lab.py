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


async def _connected_client() -> CapitalComClient:
    client = CapitalComClient()  # demo creds from settings (use_demo=True)
    await client.connect()
    return client


async def cmd_discover() -> None:
    client = await _connected_client()
    try:
        acc = await discover_account(client)
        print(f"experiment account '{EXPERIMENT_ACCOUNT_NAME}' -> accountId = {acc}")
        print("Set CAPITAL_EXPERIMENT_ACCOUNT_ID in .env to this value." if acc
              else "NOT FOUND — create/rename the demo account first.")
    finally:
        await client.close()


async def cmd_validate_isolation() -> None:
    """Task 11 gate: prove switching the experiment session does NOT move the
    soak session's active account. Uses TWO independent clients (two CSTs)."""
    s = get_settings()
    exp_id = s.capital_experiment_account_id
    assert exp_id, "set CAPITAL_EXPERIMENT_ACCOUNT_ID first (run discover-account)"
    soak = await _connected_client()
    exp = await _connected_client()
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
    client = await _connected_client()
    try:
        ex = _make_executor(client, dry_run=True)
        sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                    eod_flatten_utc=get_settings().forward_lab_eod_flatten_utc)
        await sched.on_session_open()
    finally:
        await client.close()


async def cmd_mark() -> None:
    s = get_settings()
    client = await _connected_client()
    try:
        await client.switch_account(s.capital_experiment_account_id)
        ex = _make_executor(client, dry_run=False)
        sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                    eod_flatten_utc=s.forward_lab_eod_flatten_utc)
        await sched.mark_pass()
    finally:
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
    elif cmd == "status":
        cmd_status()
    elif cmd == "score":
        cmd_score()
    else:
        print(f"unknown command {cmd!r} — see module docstring for subcommands")


if __name__ == "__main__":
    main()
