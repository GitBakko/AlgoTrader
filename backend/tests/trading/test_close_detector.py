"""Unit tests for close-detection v2 (``src.trading.close_detector``).

Drive every branch of the matcher:

* Happy path — activity + TRADE + FX all succeed.
* Ambiguous candidates — most-recent picked.
* No activity → ``Deferred(no_activity_event)``.
* Reverse-direction mismatch → ignored.
* Activity dated before ``opened_at`` → ignored.
* Epic mismatch → ignored.
* Entry-price outside tolerance → ignored.
* Activity found but TRADE missing → ``Deferred(no_transaction_yet)``.
* FX unavailable → ``Unreconciled(fx_unavailable)``.
* Same-currency passthrough.
* Foreign currency actually converts.
* TRADE row with no parseable P&L → ``Unreconciled(txn_pnl_missing)``.
* Activity with no level → ``Unreconciled(activity_level_missing)``.
* No disappeared positions → empty list.
* ``detect`` fetches windows from broker when inputs omitted.

Background: `calm-questing-quail.md`, memory
`project_capital_com_dealid_mutation.md`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.broker.fx import FxConverter, FxUnavailableError
from src.broker.models import (
    ActivityEvent,
    ActivityEventDetails,
    Direction,
    Transaction,
)
from src.trading.close_detector import (
    CloseDetector,
    Deferred,
    Reconciled,
    Unreconciled,
)


# ===== Test fixtures =====


class _FakeFx(FxConverter):
    """FX stub — never calls FRED, controllable behavior."""

    def __init__(
        self,
        *,
        rates: dict[tuple[str, str], float] | None = None,
        raise_for: set[tuple[str, str]] | None = None,
    ) -> None:
        self._rates = rates or {}
        self._raise_for = raise_for or set()
        self.calls: list[tuple[float, str | None, str | None]] = []

    async def convert(
        self,
        amount: float,
        from_ccy: str | None,
        to_ccy: str | None,
        at: datetime | None = None,
    ) -> float:
        from src.broker.fx import normalize_currency

        src = normalize_currency(from_ccy)
        dst = normalize_currency(to_ccy)
        self.calls.append((amount, from_ccy, to_ccy))
        if (src, dst) in self._raise_for:
            raise FxUnavailableError(f"test forced unavailable for {src}->{dst}")
        if src == dst:
            return amount
        rate = self._rates.get((src, dst))
        if rate is None:
            raise FxUnavailableError(f"test: no rate for {src}->{dst}")
        return amount * rate


def _make_position_dict(
    *,
    deal_id: str = "00000001-0000-0000-0000-000000000001",
    epic: str = "DE40",
    direction: str = "SELL",
    level: float = 24245.3,
    size: float = 0.181,
    opened_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "deal_id": deal_id,
        "epic": epic,
        "direction": direction,
        "level": level,
        "size": size,
        "opened_at": (opened_at or datetime(2026, 4, 21, 16, 24, 55, tzinfo=UTC)).isoformat(),
    }


def _make_close_activity(
    *,
    epic: str = "DE40",
    deal_id: str = "07101627-0015-549e-0000-0000810436be",
    source: str = "TP",
    direction: Direction = Direction.BUY,
    open_price: float = 24245.3,
    level: float = 24107.3,
    date: datetime | None = None,
) -> ActivityEvent:
    d = date or datetime(2026, 4, 21, 19, 42, 9, tzinfo=UTC)
    return ActivityEvent(
        date=d,
        dateUTC=d,
        epic=epic,
        dealId=deal_id,
        source=source,
        type="POSITION",
        status="ACCEPTED",
        details=ActivityEventDetails(
            dealReference=f"p_{deal_id}",
            marketName=epic,
            currency="EUR",
            size=0.181,
            direction=direction,
            level=level,
            openPrice=open_price,
        ),
    )


def _make_trade_txn(
    *,
    deal_id: str = "07101627-0015-549e-0000-0000810436be",
    size: str | float = "29.28",
    currency: str = "USDd",
) -> Transaction:
    return Transaction(
        date=datetime(2026, 4, 21, 19, 42, 9, tzinfo=UTC),
        dateUtc=datetime(2026, 4, 21, 19, 42, 9, tzinfo=UTC),
        instrumentName="DE40",
        transactionType="TRADE",
        reference="125678669418985",
        dealId=deal_id,
        size=size,
        currency=currency,
        note="Trade closed",
        status="PROCESSED",
    )


def _mk(fx: FxConverter | None = None, **kwargs: Any) -> CloseDetector:
    return CloseDetector(fx_converter=fx or _FakeFx(), **kwargs)


# ===== Tests =====


@pytest.mark.asyncio
async def test_happy_path_tp_close_reconciled():
    prev = _make_position_dict()
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[_make_close_activity()],
        transactions=[_make_trade_txn()],
    )
    assert len(outcomes) == 1
    out = outcomes[0]
    assert isinstance(out, Reconciled)
    assert out.deal_id == prev["deal_id"]
    assert out.close_dealid == "07101627-0015-549e-0000-0000810436be"
    assert out.pnl == pytest.approx(29.28)
    assert out.exit_price == pytest.approx(24107.3)
    assert out.close_reason == "TAKE_PROFIT_HIT"


@pytest.mark.asyncio
async def test_ambiguous_candidates_picks_most_recent():
    prev = _make_position_dict()
    early = _make_close_activity(
        deal_id="dead-early",
        date=datetime(2026, 4, 21, 18, 30, tzinfo=UTC),
    )
    late = _make_close_activity(
        deal_id="dead-late",
        date=datetime(2026, 4, 21, 19, 42, tzinfo=UTC),
    )
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[early, late],
        transactions=[
            _make_trade_txn(deal_id="dead-late"),
            _make_trade_txn(deal_id="dead-early"),
        ],
    )
    assert isinstance(outcomes[0], Reconciled)
    assert outcomes[0].close_dealid == "dead-late"


@pytest.mark.asyncio
async def test_no_activity_event_returns_deferred():
    prev = _make_position_dict()
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[],
        transactions=[],
    )
    assert isinstance(outcomes[0], Deferred)
    assert outcomes[0].reason == "no_activity_event"


@pytest.mark.asyncio
async def test_reverse_direction_wrong_is_ignored():
    # prev SELL → close event must be BUY. Here we emit a BUY-position that
    # was closed via a SELL activity — same direction → must not match.
    prev = _make_position_dict(direction="BUY")
    wrong = _make_close_activity(direction=Direction.BUY)  # should be SELL
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[wrong],
        transactions=[_make_trade_txn()],
    )
    assert isinstance(outcomes[0], Deferred)
    assert outcomes[0].reason == "no_activity_event"


@pytest.mark.asyncio
async def test_activity_before_opened_at_is_ignored():
    opened = datetime(2026, 4, 21, 20, 0, tzinfo=UTC)
    prev = _make_position_dict(opened_at=opened)
    stale = _make_close_activity(date=datetime(2026, 4, 21, 19, 0, tzinfo=UTC))
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[stale],
        transactions=[_make_trade_txn()],
    )
    assert isinstance(outcomes[0], Deferred)


@pytest.mark.asyncio
async def test_epic_mismatch_is_ignored():
    prev = _make_position_dict(epic="DE40")
    other = _make_close_activity(epic="OIL_CRUDE")
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[other],
        transactions=[_make_trade_txn()],
    )
    assert isinstance(outcomes[0], Deferred)


@pytest.mark.asyncio
async def test_broker_epic_mapping_matches_display_epic():
    """Position stores display epic ('WTIUSD'); Capital.com activity reports
    broker epic ('OIL_CRUDE'). EPIC_TO_BROKER mapping must bridge them so
    the match succeeds."""
    prev = _make_position_dict(epic="WTIUSD", level=86.21)
    activity = _make_close_activity(
        epic="OIL_CRUDE", open_price=86.21, deal_id="close-oil"
    )
    txn = _make_trade_txn(deal_id="close-oil", size="-20.27")
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[activity],
        transactions=[txn],
    )
    assert isinstance(outcomes[0], Reconciled)
    assert outcomes[0].pnl == -20.27


@pytest.mark.asyncio
async def test_entry_price_outside_tolerance_is_ignored():
    prev = _make_position_dict(level=24245.3)
    # 24500 is ~1% off — well beyond the default 0.1% tolerance
    far = _make_close_activity(open_price=24500.0)
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[far],
        transactions=[_make_trade_txn()],
    )
    assert isinstance(outcomes[0], Deferred)


@pytest.mark.asyncio
async def test_activity_found_but_trade_missing_returns_deferred():
    prev = _make_position_dict()
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[_make_close_activity()],
        transactions=[],
    )
    assert isinstance(outcomes[0], Deferred)
    assert outcomes[0].reason == "no_transaction_yet"


@pytest.mark.asyncio
async def test_fx_unavailable_returns_unreconciled():
    prev = _make_position_dict()
    fx = _FakeFx(raise_for={("EUR", "USD")})
    detector = _mk(fx=fx, account_currency="USD")
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[_make_close_activity()],
        transactions=[_make_trade_txn(currency="EUR")],
    )
    assert isinstance(outcomes[0], Unreconciled)
    assert outcomes[0].reason == "fx_unavailable"


@pytest.mark.asyncio
async def test_same_currency_passthrough_does_not_call_fred():
    prev = _make_position_dict()
    fx = _FakeFx()  # no rates registered — would raise on real lookup
    detector = _mk(fx=fx, account_currency="USD")
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[_make_close_activity()],
        transactions=[_make_trade_txn(currency="USDd")],  # normalizes to USD
    )
    assert isinstance(outcomes[0], Reconciled)
    assert outcomes[0].pnl == pytest.approx(29.28)


@pytest.mark.asyncio
async def test_foreign_currency_converts_via_fx():
    prev = _make_position_dict()
    fx = _FakeFx(rates={("EUR", "USD"): 1.1})
    detector = _mk(fx=fx, account_currency="USD")
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[_make_close_activity()],
        transactions=[_make_trade_txn(currency="EUR", size="10.00")],
    )
    assert isinstance(outcomes[0], Reconciled)
    assert outcomes[0].pnl == pytest.approx(11.0)


@pytest.mark.asyncio
async def test_txn_pnl_missing_returns_unreconciled():
    prev = _make_position_dict()
    # SWAP row has no P&L semantics for our purposes — emulate by injecting
    # an empty TRADE row.
    bad = _make_trade_txn(size="")
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[_make_close_activity()],
        transactions=[bad],
    )
    assert isinstance(outcomes[0], Unreconciled)
    assert outcomes[0].reason == "txn_pnl_missing"


@pytest.mark.asyncio
async def test_activity_level_missing_returns_unreconciled():
    prev = _make_position_dict()
    act = _make_close_activity()
    # Patch the Pydantic model instance to remove the level.
    act.details.level = None
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[act],
        transactions=[_make_trade_txn()],
    )
    assert isinstance(outcomes[0], Unreconciled)
    assert outcomes[0].reason == "activity_level_missing"


@pytest.mark.asyncio
async def test_no_disappeared_positions_returns_empty():
    prev = _make_position_dict()
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[{"deal_id": prev["deal_id"]}],  # still open
        activities=[],
        transactions=[],
    )
    assert outcomes == []


@pytest.mark.asyncio
async def test_detect_fetches_windows_from_broker_when_not_injected():
    prev = _make_position_dict(
        opened_at=datetime(2026, 4, 21, 16, 0, tzinfo=UTC),
    )

    class _Broker:
        def __init__(self) -> None:
            self.activity_called_with: tuple[datetime, datetime] | None = None
            self.transactions_called_with: tuple[datetime, datetime] | None = None

        async def get_activity_history(self, from_date, to_date):
            self.activity_called_with = (from_date, to_date)
            return [_make_close_activity()]

        async def get_transaction_history(self, from_date, to_date):
            self.transactions_called_with = (from_date, to_date)
            return [_make_trade_txn()]

    broker = _Broker()
    detector = CloseDetector(broker=broker, fx_converter=_FakeFx())

    now = datetime(2026, 4, 21, 20, 0, tzinfo=UTC)
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        now=now,
    )
    assert isinstance(outcomes[0], Reconciled)
    # Window: from = opened_at - 240min (default lookback widened to absorb
    # Capital.com's naive-Berlin createdDate offset), to = now - 60s
    # (clamped down from now + 1min because Capital.com /history/* rejects
    # any `to` in the future with `error.invalid.daterange`).
    assert broker.activity_called_with == (
        datetime(2026, 4, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 4, 21, 19, 59, tzinfo=UTC),
    )
    assert broker.transactions_called_with == broker.activity_called_with


@pytest.mark.asyncio
async def test_naive_opened_at_parsed_as_europe_berlin():
    """Capital.com /positions returns createdDate as a naive wall-clock
    string in Europe/Berlin. Prior behaviour treated the naive value as
    UTC and pushed the activity window 2h into the future, silently
    missing every real close event. Regression guard: a naive opened_at
    must still match an activity whose dateUTC is 2h earlier."""
    # Open in Europe/Berlin 14:16 (summer time) == 12:16 UTC.
    prev = _make_position_dict(
        epic="NATGAS",
        level=2.8455,
        direction="SELL",
    )
    prev["opened_at"] = "2026-04-22T14:16:50"  # naive Berlin

    # Close activity emitted at 13:02 UTC — before the fake "14:16 UTC"
    # but after the real 12:16 UTC open.
    close_act = ActivityEvent(
        date=datetime(2026, 4, 22, 15, 2, 0),  # naive Berlin
        dateUTC=datetime(2026, 4, 22, 13, 2, 0, tzinfo=UTC),
        epic="NATGAS",
        source="SL",
        type="POSITION",
        status="ACCEPTED",
        dealId="close-natgas",
        details=ActivityEventDetails(
            openPrice=2.8455,
            level=2.8600,
            direction=Direction.BUY,  # opposite of SELL position
            currency="USD",
        ),
    )
    txn = _make_trade_txn(deal_id="close-natgas", size="-60.90")

    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[close_act],
        transactions=[txn],
    )
    assert isinstance(outcomes[0], Reconciled), outcomes[0]
    assert outcomes[0].pnl == pytest.approx(-60.90)


@pytest.mark.asyncio
async def test_detect_requires_broker_or_injected_lists():
    prev = _make_position_dict()
    detector = CloseDetector(fx_converter=_FakeFx())  # no broker
    with pytest.raises(RuntimeError):
        await detector.detect(
            previous={prev["deal_id"]: prev},
            current=[],
        )


@pytest.mark.asyncio
async def test_close_reason_labels_map_correctly():
    prev = _make_position_dict()
    cases = [
        ("TP", "TAKE_PROFIT_HIT"),
        ("SL", "STOP_LOSS_HIT"),
        ("STOP_OUT", "LIQUIDATION"),
        ("USER", "USER_CLOSE"),
        ("SYSTEM", "SYSTEM_CLOSE"),
    ]
    detector = _mk()
    for src, expected in cases:
        outcomes = await detector.detect(
            previous={prev["deal_id"]: prev},
            current=[],
            activities=[_make_close_activity(source=src)],
            transactions=[_make_trade_txn()],
        )
        assert isinstance(outcomes[0], Reconciled)
        assert outcomes[0].close_reason == expected, (
            f"Expected {src} → {expected}, got {outcomes[0].close_reason}"
        )


@pytest.mark.asyncio
async def test_position_still_open_is_skipped_even_with_disappeared_sibling():
    open_pos = _make_position_dict(deal_id="open-1", level=100.0)
    closed_pos = _make_position_dict(
        deal_id="closed-1",
        level=24245.3,
    )
    detector = _mk()
    outcomes = await detector.detect(
        previous={open_pos["deal_id"]: open_pos, closed_pos["deal_id"]: closed_pos},
        current=[open_pos],
        activities=[_make_close_activity()],
        transactions=[_make_trade_txn()],
    )
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], Reconciled)
    assert outcomes[0].deal_id == "closed-1"


@pytest.mark.asyncio
async def test_close_event_without_open_price_is_ignored():
    prev = _make_position_dict()
    act = _make_close_activity()
    act.details.open_price = None  # opens don't have openPrice, must be rejected
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[act],
        transactions=[_make_trade_txn()],
    )
    assert isinstance(outcomes[0], Deferred)
    assert outcomes[0].reason == "no_activity_event"


@pytest.mark.asyncio
async def test_non_close_source_is_ignored():
    # DEPOSIT source is NOT in CLOSE_SOURCES — activity must not count.
    prev = _make_position_dict()
    non_close = _make_close_activity(source="DEPOSIT")
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[non_close],
        transactions=[_make_trade_txn()],
    )
    assert isinstance(outcomes[0], Deferred)


@pytest.mark.asyncio
async def test_non_trade_transaction_ignored_in_match():
    prev = _make_position_dict()
    swap = _make_trade_txn()
    swap.transaction_type = "SWAP"
    trade = _make_trade_txn()
    detector = _mk()
    outcomes = await detector.detect(
        previous={prev["deal_id"]: prev},
        current=[],
        activities=[_make_close_activity()],
        transactions=[swap, trade],
    )
    # The real TRADE row should still be picked.
    assert isinstance(outcomes[0], Reconciled)


@pytest.mark.asyncio
async def test_resolves_multiple_disappeared_positions_independently():
    a = _make_position_dict(deal_id="pos-A", level=24245.3, epic="DE40")
    b = _make_position_dict(
        deal_id="pos-B",
        level=86.924,
        epic="OIL_CRUDE",
        direction="SELL",
    )
    act_a = _make_close_activity(
        deal_id="close-A", epic="DE40", open_price=24245.3
    )
    act_b = _make_close_activity(
        deal_id="close-B",
        epic="OIL_CRUDE",
        open_price=86.924,
        level=85.0,
        source="SL",
    )
    txn_a = _make_trade_txn(deal_id="close-A", size="29.28")
    txn_b = _make_trade_txn(deal_id="close-B", size="-20.27")
    detector = _mk()
    outcomes = await detector.detect(
        previous={a["deal_id"]: a, b["deal_id"]: b},
        current=[],
        activities=[act_a, act_b],
        transactions=[txn_a, txn_b],
    )
    assert len(outcomes) == 2
    by_id = {o.deal_id: o for o in outcomes}
    assert isinstance(by_id["pos-A"], Reconciled)
    assert by_id["pos-A"].pnl == pytest.approx(29.28)
    assert by_id["pos-A"].close_reason == "TAKE_PROFIT_HIT"
    assert isinstance(by_id["pos-B"], Reconciled)
    assert by_id["pos-B"].pnl == pytest.approx(-20.27)
    assert by_id["pos-B"].close_reason == "STOP_LOSS_HIT"
