from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from loguru import logger

from src.broker.models import CreatePositionRequest
from forward.strategy import ForwardStrategy, MarketContext, Signal


class IsolationError(RuntimeError):
    """Raised when the active broker account is NOT the experiment account.
    Hard guard against ever trading on the soak account."""


@dataclass
class ExperimentExecutor:
    client: object              # CapitalComClient, connected + switched to experiment account
    experiment_account_id: str
    ledger: object              # ForwardLedger
    notional_usd: float = 200.0
    max_concurrent: int = 5
    daily_loss_limit_usd: float = 100.0
    dry_run: bool = True
    _halted: bool = field(default=False, init=False, repr=False)

    async def assert_isolation(self) -> None:
        active = await self.client.get_active_account_id()
        if active != self.experiment_account_id:
            raise IsolationError(
                f"active account {active!r} != experiment {self.experiment_account_id!r} "
                "— refusing to trade (soak-protection guard)")

    def _size_for(self, price: float) -> float:
        return round(self.notional_usd / price, 4)

    async def try_enter(self, strat: ForwardStrategy, ctx: MarketContext,
                        session_date: str) -> Signal | object | None:
        if self._halted:
            return None
        if len(self.ledger.list_open()) >= self.max_concurrent:
            logger.warning(f"[forward-lab] max_concurrent={self.max_concurrent} reached — skip")
            return None
        sig = strat.should_enter(ctx)
        if sig is None:
            return None
        size = self._size_for(ctx.today_open)
        if self.dry_run:
            logger.info(f"[DRY-RUN] {strat.name} {sig.direction.value} {sig.epic} "
                        f"size={size} sl={sig.stop_level:.4f} :: {sig.rationale}")
            return sig
        await self.assert_isolation()  # MUST pass before any real order
        req = CreatePositionRequest(epic=sig.epic, direction=sig.direction,
                                    size=size, stop_level=sig.stop_level)
        conf = await self.client.create_position(req)
        self.ledger.record_open(
            strategy=strat.name, epic=sig.epic, session_date=session_date,
            deal_id=conf.deal_id, direction=sig.direction.value, entry=conf.level,
            size=size, stop_level=sig.stop_level, rationale=sig.rationale,
            opened_at=datetime.now(timezone.utc).isoformat())
        logger.success(f"[LIVE] opened {sig.epic} {sig.direction.value} "
                       f"dealId={conf.deal_id} @ {conf.level}")
        return conf
