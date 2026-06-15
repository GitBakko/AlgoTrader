from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from src.broker.models import CreatePositionRequest, Direction
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
    daily_loss_limit_eur: float = 100.0
    account_ccy: str = "EUR"   # experiment account denomination (broker P&L arrives in this ccy)
    dry_run: bool = True

    async def assert_isolation(self) -> None:
        active = await self.client.get_active_account_id()
        if active != self.experiment_account_id:
            raise IsolationError(
                f"active account {active!r} != experiment {self.experiment_account_id!r} "
                "— refusing to trade (soak-protection guard)")

    def _size_for(self, price: float) -> float:
        return round(self.notional_usd / price, 4)

    async def _broker_safe_stop(self, sig, ref_price: float) -> float | None:
        """Validate/clamp the signal stop against the LIVE price before sending.

        Strategies anchor stops to today_open / opening-range levels, but
        Capital.com validates the stop relative to the *current* market price.
        A fast move (e.g. a gap-up that keeps running) can leave a fade-short
        stop *below* spot — a wrong-side stop the broker rejects with
        ``error.invalid.stoploss.minvalue``. Returns:
          • the signal stop unchanged when it already clears the broker minimum,
          • a nudged stop when it is the correct side but inside the minimum,
          • ``None`` when it is on the wrong side of spot (skip — the fade/breakout
            thesis is already invalidated by the move).
        """
        try:
            details = await self.client.get_market_details(sig.epic)
            rules = details.get("dealingRules", {})
            msd = rules.get("minStopOrProfitDistance", {}) or {}
            unit, val = msd.get("unit"), msd.get("value")
            if not isinstance(val, (int, float)):
                return sig.stop_level  # rules unavailable (e.g. mocked) — trust the signal
            min_dist = ref_price * float(val) / 100.0 if unit == "PERCENTAGE" else float(val)
        except Exception as e:  # noqa: BLE001 — a recon GET must never block an entry
            logger.warning(f"[forward-lab] {sig.epic} dealingRules fetch failed: {e} "
                           "— sending signal stop unchecked")
            return sig.stop_level
        pad = min_dist * 1.10 + ref_price * 5e-4  # margin over the raw broker minimum + spread
        if sig.direction == Direction.SELL:        # SELL stop must sit ABOVE the entry
            if sig.stop_level <= ref_price:
                return None                          # wrong side — skip
            return max(sig.stop_level, ref_price + pad)
        if sig.stop_level >= ref_price:              # BUY stop must sit BELOW the entry
            return None                              # wrong side — skip
        return min(sig.stop_level, ref_price - pad)

    async def try_enter(self, strat: ForwardStrategy, ctx: MarketContext,
                        session_date: str) -> Signal | object | None:
        net_today = self.ledger.session_net(session_date)
        if net_today <= -self.daily_loss_limit_eur:
            logger.critical(
                f"[forward-lab] DAILY LOSS LIMIT: session {session_date} realized "
                f"{net_today:+.2f} {self.account_ccy} <= -{self.daily_loss_limit_eur:.2f} "
                "— blocking new entries (open positions keep broker SL + EOD flatten)")
            return None
        if self.ledger.exists(strat.name, ctx.epic, session_date):
            return None                              # one trade per strategy/epic/day (idempotent)
        if len(self.ledger.list_open()) >= self.max_concurrent:
            logger.warning(f"[forward-lab] max_concurrent={self.max_concurrent} reached — skip")
            return None
        sig = strat.should_enter(ctx)
        if sig is None:
            return None
        size = self._size_for(ctx.current_price)
        if self.dry_run:
            logger.info(f"[DRY-RUN] {strat.name} {sig.direction.value} {sig.epic} "
                        f"size={size} sl={sig.stop_level:.4f} :: {sig.rationale}")
            return sig
        await self.assert_isolation()  # MUST pass before any real order
        stop_level = await self._broker_safe_stop(sig, ctx.current_price)
        if stop_level is None:
            logger.warning(
                f"[forward-lab] {strat.name} {sig.epic} {sig.direction.value} stop "
                f"{sig.stop_level:.4f} is on the wrong side of live {ctx.current_price:.4f} "
                "— skip (price ran past the entry stop; fade/breakout thesis invalidated)")
            return None
        req = CreatePositionRequest(epic=sig.epic, direction=sig.direction,
                                    size=size, stop_level=stop_level)
        conf = await self.client.create_position(req)
        self.ledger.record_open(
            strategy=strat.name, epic=sig.epic, session_date=session_date,
            deal_id=conf.deal_id, direction=sig.direction.value, entry=conf.level,
            size=size, stop_level=stop_level, rationale=sig.rationale,
            opened_at=datetime.now(timezone.utc).isoformat(),
            prev_close=ctx.prev_close, today_open=ctx.today_open)
        logger.success(f"[LIVE] opened {sig.epic} {sig.direction.value} "
                       f"dealId={conf.deal_id} @ {conf.level}")
        return conf
