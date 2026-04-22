"""Close-detection v2 — activity-as-source-of-truth.

Given a set of positions that disappeared between two broker snapshots, the
detector resolves each one deterministically:

1. `/history/activity` is scanned for ``POSITION / ACCEPTED`` events whose
   ``source`` is a close source (TP, SL, STOP_OUT, MARGIN_CALL, USER,
   SYSTEM, DEALER) and that carry ``details.openPrice``. Each disappeared
   Position is matched on
   ``(epic, openPrice ≈ entry_price, reverse direction, date > opened_at)``.
2. The matched activity's ``dealId`` is looked up in a TRADE row from
   ``/history/transactions``. That row carries the realized P&L (in
   transaction currency).
3. The P&L is run through :class:`~src.broker.fx.FxConverter` so a foreign-
   currency transaction never lands silently against a different account
   currency.

Outcomes:

- :class:`Reconciled`: activity + TRADE + FX all succeeded.
- :class:`Deferred`: the chain is not yet complete (activity not emitted,
  TRADE not yet settled) — caller should retry on the next loop tick.
- :class:`Unreconciled`: hard stop that should be persisted as UNRECONCILED
  (FX series unavailable, TRADE row missing P&L, activity missing exit level).

The detector is pure resolution logic: it does not write to the DB, does
not mutate ``_pending_close_detections``, and does not touch Prometheus.
Callers own persistence and metrics.

See plan `calm-questing-quail.md` and memory
`project_capital_com_dealid_mutation.md` for the root-cause background that
motivated v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from src.broker.client import EPIC_TO_BROKER
from src.broker.fx import FxConverter, FxUnavailableError
from src.broker.models import ActivityEvent, Transaction

# ===== Outcome types =====


@dataclass(frozen=True)
class Reconciled:
    """Close linked to broker truth — caller writes real P&L + exit price."""

    deal_id: str  # Position.deal_id (the row being closed)
    close_dealid: str  # close-side dealId (activity / TRADE row) — audit only
    pnl: float  # realized, in account currency, post-FX
    exit_price: float  # from activity.details.level (TP/SL trigger)
    close_reason: str  # TAKE_PROFIT_HIT / STOP_LOSS_HIT / USER_CLOSE / ...
    activity: ActivityEvent
    transaction: Transaction


@dataclass(frozen=True)
class Deferred:
    """Retry — activity or TRADE not yet visible on the REST API."""

    deal_id: str
    reason: str  # "no_activity_event" | "no_transaction_yet"


@dataclass(frozen=True)
class Unreconciled:
    """Hard stop — caller persists pnl=NULL + alert."""

    deal_id: str
    reason: str  # "fx_unavailable" | "txn_pnl_missing" | "activity_level_missing"


CloseOutcome = Reconciled | Deferred | Unreconciled


# ===== Defaults =====

DEFAULT_ENTRY_PRICE_TOLERANCE_PCT = 0.001  # 0.1%
DEFAULT_ACTIVITY_WINDOW_LOOKBACK_MINUTES = 5
DEFAULT_ACTIVITY_WINDOW_FUTURE_MINUTES = 1


# ===== Helpers =====


def _parse_opened_at(value: Any) -> datetime | None:
    """Accept either datetime or ISO string, always return UTC-aware."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _activity_date_utc(act: ActivityEvent) -> datetime:
    """Return activity timestamp as UTC-aware datetime."""
    d = act.date_utc or act.date
    if d.tzinfo is None:
        return d.replace(tzinfo=UTC)
    return d.astimezone(UTC)


def _opposite_direction(direction: str) -> str:
    return "SELL" if (direction or "").upper() == "BUY" else "BUY"


# ===== Detector =====


class CloseDetector:
    """Activity-as-SoT close detector.

    Pure resolution. Fetching is optional (inject ``activities`` /
    ``transactions`` in :meth:`detect` to drive tests) but when a broker
    client is supplied at construction time the detector can fetch its own
    windows covering every disappeared Position's ``opened_at``.
    """

    def __init__(
        self,
        *,
        broker: Any = None,
        fx_converter: FxConverter,
        account_currency: str = "USD",
        entry_price_tolerance_pct: float = DEFAULT_ENTRY_PRICE_TOLERANCE_PCT,
        activity_window_lookback_minutes: int = DEFAULT_ACTIVITY_WINDOW_LOOKBACK_MINUTES,
        activity_window_future_minutes: int = DEFAULT_ACTIVITY_WINDOW_FUTURE_MINUTES,
    ) -> None:
        self._broker = broker
        self._fx = fx_converter
        self._account_currency = account_currency
        self._entry_tol_pct = entry_price_tolerance_pct
        self._window_back_min = activity_window_lookback_minutes
        self._window_forward_min = activity_window_future_minutes

    async def detect(
        self,
        previous: dict[str, dict],
        current: list[dict],
        *,
        activities: list[ActivityEvent] | None = None,
        transactions: list[Transaction] | None = None,
        now: datetime | None = None,
    ) -> list[CloseOutcome]:
        """Resolve every Position in ``previous`` that is missing from ``current``.

        Returns one outcome per disappeared Position, in the same order as
        ``previous``. Positions present in both snapshots are ignored.
        """
        current_deals = {p.get("deal_id") for p in current if p.get("deal_id")}
        disappeared = [
            (did, ppos) for did, ppos in previous.items() if did and did not in current_deals
        ]
        if not disappeared:
            return []

        now_utc = now or datetime.now(UTC)

        if activities is None or transactions is None:
            if self._broker is None:
                raise RuntimeError(
                    "CloseDetector.detect: no broker client to fetch activity/"
                    "transactions with, and none were injected."
                )
            from_dt, to_dt = self._compute_window(disappeared, now_utc)
            if activities is None:
                activities = await self._broker.get_activity_history(from_dt, to_dt)
            if transactions is None:
                transactions = await self._broker.get_transaction_history(from_dt, to_dt)

        outcomes: list[CloseOutcome] = []
        for deal_id, prev_pos in disappeared:
            outcomes.append(await self._resolve_one(deal_id, prev_pos, activities, transactions))
        return outcomes

    # ----- internals -----

    def _compute_window(
        self,
        disappeared: list[tuple[str, dict]],
        now_utc: datetime,
    ) -> tuple[datetime, datetime]:
        earliest_open = now_utc
        for _, ppos in disappeared:
            opened = _parse_opened_at(ppos.get("opened_at"))
            if opened and opened < earliest_open:
                earliest_open = opened
        from_dt = earliest_open - timedelta(minutes=self._window_back_min)
        to_dt = now_utc + timedelta(minutes=self._window_forward_min)
        return from_dt, to_dt

    async def _resolve_one(
        self,
        deal_id: str,
        prev_pos: dict,
        activities: list[ActivityEvent],
        transactions: list[Transaction],
    ) -> CloseOutcome:
        activity = self._match_activity(prev_pos, activities)
        if activity is None:
            return Deferred(deal_id=deal_id, reason="no_activity_event")

        txn = self._match_transaction(activity, transactions)
        if txn is None:
            return Deferred(deal_id=deal_id, reason="no_transaction_yet")

        pnl_raw = txn.pl_value
        if pnl_raw is None:
            return Unreconciled(deal_id=deal_id, reason="txn_pnl_missing")

        try:
            pnl = await self._fx.convert(pnl_raw, txn.currency, self._account_currency)
        except FxUnavailableError as exc:
            logger.warning(
                f"[{prev_pos.get('epic', '?')}] FX unavailable for {deal_id} "
                f"(txn={txn.currency!r}, account={self._account_currency!r}): {exc}"
            )
            return Unreconciled(deal_id=deal_id, reason="fx_unavailable")

        exit_price = activity.details.level
        if exit_price is None:
            # Using entry_price here would mask P&L as zero — refuse.
            return Unreconciled(deal_id=deal_id, reason="activity_level_missing")

        return Reconciled(
            deal_id=deal_id,
            close_dealid=activity.deal_id,
            pnl=float(pnl),
            exit_price=float(exit_price),
            close_reason=activity.close_reason_label(),
            activity=activity,
            transaction=txn,
        )

    def _match_activity(
        self,
        prev_pos: dict,
        activities: list[ActivityEvent],
    ) -> ActivityEvent | None:
        epic = prev_pos.get("epic")
        direction = (prev_pos.get("direction") or "").upper()
        entry_raw = prev_pos.get("level")
        opened_at = _parse_opened_at(prev_pos.get("opened_at"))
        if not epic or not direction or entry_raw is None:
            return None
        try:
            entry = float(entry_raw)
        except (TypeError, ValueError):
            return None

        expected_reverse = _opposite_direction(direction)
        tolerance = abs(entry) * self._entry_tol_pct

        # Capital.com /history/activity reports `epic` in broker form
        # (e.g. "OIL_CRUDE") while our Position row stores the display form
        # ("WTIUSD"). Accept either side via EPIC_TO_BROKER so symbols that
        # the broker renames still pair.
        broker_epic = EPIC_TO_BROKER.get(epic, epic)

        candidates: list[ActivityEvent] = []
        for act in activities:
            if not act.is_close_event():
                continue
            if act.epic != epic and act.epic != broker_epic:
                continue
            op = act.details.open_price
            if op is None:
                continue
            try:
                if abs(float(op) - entry) > tolerance:
                    continue
            except (TypeError, ValueError):
                continue
            act_dir = act.details.direction
            if act_dir is None or act_dir.value.upper() != expected_reverse:
                continue
            if opened_at is not None and _activity_date_utc(act) <= opened_at:
                continue
            candidates.append(act)

        if not candidates:
            return None
        candidates.sort(key=_activity_date_utc, reverse=True)
        return candidates[0]

    @staticmethod
    def _match_transaction(
        activity: ActivityEvent,
        transactions: list[Transaction],
    ) -> Transaction | None:
        target = activity.deal_id
        if not target:
            return None
        for txn in transactions:
            if (txn.transaction_type or "").upper() != "TRADE":
                continue
            if txn.deal_id == target:
                return txn
        return None


__all__ = [
    "CloseDetector",
    "CloseOutcome",
    "Deferred",
    "Reconciled",
    "Unreconciled",
]
