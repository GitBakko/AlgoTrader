from __future__ import annotations

import sqlite3
from pathlib import Path


class ForwardLedger:
    """Per-trade forward ledger (SQLite). One open row per (strategy, epic,
    session_date) — idempotent so a re-fired scheduler trigger never double-opens."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS trades(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy TEXT NOT NULL, epic TEXT NOT NULL,
                    session_date TEXT NOT NULL, deal_id TEXT,
                    direction TEXT, entry REAL, size REAL, stop_level REAL,
                    rationale TEXT, opened_at TEXT,
                    exit_price REAL, net_pnl REAL, closed_at TEXT, close_reason TEXT,
                    UNIQUE(strategy, epic, session_date))"""
            )

    def record_open(self, *, strategy: str, epic: str, session_date: str, deal_id: str,
                    direction: str, entry: float, size: float, stop_level: float,
                    rationale: str, opened_at: str) -> bool:
        try:
            with self._conn() as c:
                c.execute(
                    """INSERT INTO trades(strategy,epic,session_date,deal_id,direction,
                       entry,size,stop_level,rationale,opened_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (strategy, epic, session_date, deal_id, direction, entry, size,
                     stop_level, rationale, opened_at),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def list_open(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM trades WHERE closed_at IS NULL")]

    def record_close(self, *, deal_id: str, exit_price: float, net_pnl: float,
                     closed_at: str, close_reason: str) -> None:
        with self._conn() as c:
            c.execute(
                """UPDATE trades SET exit_price=?, net_pnl=?, closed_at=?, close_reason=?
                   WHERE deal_id=? AND closed_at IS NULL""",
                (exit_price, net_pnl, closed_at, close_reason, deal_id),
            )

    def realized(self, strategy: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM trades WHERE strategy=? AND closed_at IS NOT NULL "
                "ORDER BY closed_at", (strategy,))]
