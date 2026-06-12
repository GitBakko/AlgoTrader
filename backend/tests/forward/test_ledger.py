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


def test_record_open_persists_prev_close_and_today_open(tmp_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "pc.db")
    led.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-03", deal_id="D1",
                    direction="SELL", entry=104.0, size=1.0, stop_level=106.0,
                    rationale="x", opened_at="2026-06-03T14:00:00+00:00",
                    prev_close=100.0, today_open=104.0)
    row = led.list_open()[0]
    assert row["prev_close"] == 100.0 and row["today_open"] == 104.0


def test_init_migrates_legacy_db_missing_columns(tmp_path):
    import sys, pathlib, sqlite3
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    db = tmp_path / "legacy.db"
    # simulate an OLD ledger.db without prev_close/today_open
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT NOT NULL, epic TEXT NOT NULL,
        session_date TEXT NOT NULL, deal_id TEXT, direction TEXT, entry REAL, size REAL,
        stop_level REAL, rationale TEXT, opened_at TEXT, exit_price REAL, net_pnl REAL,
        closed_at TEXT, close_reason TEXT, UNIQUE(strategy, epic, session_date))""")
    conn.commit(); conn.close()
    from forward.ledger import ForwardLedger
    led = ForwardLedger(db)   # _init must ALTER-ADD the missing columns
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(trades)")}
    assert "prev_close" in cols and "today_open" in cols
    # and a record_open with the new fields works on the migrated db
    led.record_open(strategy="orb", epic="NVDA", session_date="2026-06-03", deal_id="D2",
                    direction="BUY", entry=500.0, size=1.0, stop_level=490.0,
                    rationale="y", opened_at="2026-06-03T14:30:00+00:00",
                    prev_close=495.0, today_open=500.0)
    assert led.list_open()[0]["prev_close"] == 495.0


def test_close_deal_id_migration_and_roundtrip(tmp_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "cd.db")
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-12",
                    deal_id="D1", direction="BUY", entry=100.0, size=1.0,
                    stop_level=99.0, rationale="t", opened_at="2026-06-12T14:00:00+00:00")
    led.set_close_deal_id("D1", "DROT")
    row = led.list_open()[0]
    assert row["close_deal_id"] == "DROT"
    # re-init on the same file must be idempotent (ADD COLUMN guarded)
    ForwardLedger(tmp_path / "cd.db")


def test_session_net_sums_only_closed_rows_of_that_day(tmp_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "sn.db")
    # closed today: -60 and -50; open today: ignored; closed yesterday: ignored
    for i, (sd, pnl, closed) in enumerate([
        ("2026-06-12", -60.0, True),
        ("2026-06-12", -50.0, True),
        ("2026-06-12", None, False),
        ("2026-06-11", -500.0, True),
    ]):
        led.record_open(strategy="orb", epic=f"E{i}", session_date=sd,
                        deal_id=f"D{i}", direction="BUY", entry=100.0, size=1.0,
                        stop_level=99.0, rationale="t",
                        opened_at=f"{sd}T14:00:00+00:00")
        if closed:
            led.record_close(deal_id=f"D{i}", exit_price=99.0, net_pnl=pnl,
                             closed_at=f"{sd}T19:45:00+00:00", close_reason="BROKER_TRADE")
    assert led.session_net("2026-06-12") == -110.0
    assert led.session_net("2026-06-10") == 0.0
