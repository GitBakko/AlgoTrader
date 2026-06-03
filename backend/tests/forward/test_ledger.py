import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))


def test_ledger_open_close_roundtrip_and_idempotent(tmp_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "fl.db")
    ok = led.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-02",
                         deal_id="D1", direction="SELL", entry=103.0, size=1.94,
                         stop_level=105.0, rationale="gap +3% fade short",
                         opened_at="2026-06-02T14:00:00+00:00")
    assert ok is True
    dup = led.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-02",
                          deal_id="D2", direction="SELL", entry=103.0, size=1.94,
                          stop_level=105.0, rationale="x", opened_at="2026-06-02T14:01:00+00:00")
    assert dup is False
    assert len(led.list_open()) == 1
    led.record_close(deal_id="D1", exit_price=101.5, net_pnl=2.91,
                     closed_at="2026-06-02T16:00:00+00:00", close_reason="FILL_50")
    assert led.list_open() == []
    rz = led.realized("gap_fade")
    assert len(rz) == 1 and rz[0]["net_pnl"] == 2.91


def test_exists_true_after_open_open_or_closed(tmp_path):
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "x.db")
    assert led.exists("orb", "AAPL", "2026-06-03") is False
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-03", deal_id="D1",
                    direction="BUY", entry=100.0, size=1.0, stop_level=98.0,
                    rationale="x", opened_at="2026-06-03T14:00:00+00:00")
    assert led.exists("orb", "AAPL", "2026-06-03") is True
    led.record_close(deal_id="D1", exit_price=101.0, net_pnl=1.0,
                     closed_at="2026-06-03T16:00:00+00:00", close_reason="TP")
    assert led.exists("orb", "AAPL", "2026-06-03") is True   # still True after close
    assert led.exists("orb", "AAPL", "2026-06-04") is False    # different day
    assert led.exists("gap_fade", "AAPL", "2026-06-03") is False  # different strategy
