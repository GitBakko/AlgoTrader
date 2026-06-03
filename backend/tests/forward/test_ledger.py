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
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
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
