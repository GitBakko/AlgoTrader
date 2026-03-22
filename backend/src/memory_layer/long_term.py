# MANTIS-EVOLUTION: Long Term Memory
"""Long-term memory: persistent pattern store backed by SQLite."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.memory_layer.schemas import (
    BlacklistCondition,
    MarketPattern,
    MemoryConfig,
    MemoryItem,
)


class MantisLongTermMemory:
    """
    Long-term memory: stores market patterns and blacklist conditions in SQLite.

    Patterns are promoted from STM during daily consolidation.
    Blacklist conditions are patterns that historically produce losses.
    """

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig()
        self._db_path = Path(self.config.db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with schema."""
        schema_path = Path(__file__).parent / "schema.sql"
        with sqlite3.connect(str(self._db_path)) as conn:
            if schema_path.exists():
                conn.executescript(schema_path.read_text())
            else:
                # Inline fallback
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS long_term_patterns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pattern_id TEXT UNIQUE NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        regime TEXT NOT NULL DEFAULT '',
                        occurrence_count INTEGER NOT NULL DEFAULT 1,
                        avg_outcome REAL NOT NULL DEFAULT 0.0,
                        confidence REAL NOT NULL DEFAULT 0.0,
                        feature_signature TEXT NOT NULL DEFAULT '[]',
                        last_seen TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS blacklist_conditions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        condition_id TEXT UNIQUE NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        feature_signature TEXT NOT NULL DEFAULT '[]',
                        avg_loss REAL NOT NULL DEFAULT 0.0,
                        occurrence_count INTEGER NOT NULL DEFAULT 0,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                """)

    def add_pattern(self, pattern: MarketPattern) -> str:
        """Add or update a pattern in LTM. Returns pattern_id."""
        if not pattern.pattern_id:
            pattern.pattern_id = str(uuid.uuid4())[:8]

        now = datetime.now(timezone.utc).isoformat()
        sig_json = json.dumps(pattern.feature_signature)

        with sqlite3.connect(str(self._db_path)) as conn:
            # Try update first (increment occurrence)
            cursor = conn.execute(
                "UPDATE long_term_patterns SET occurrence_count = occurrence_count + 1, "
                "avg_outcome = ?, confidence = ?, last_seen = ?, updated_at = ?, feature_signature = ? "
                "WHERE pattern_id = ?",
                (pattern.avg_outcome, pattern.confidence, now, now, sig_json, pattern.pattern_id),
            )
            if cursor.rowcount == 0:
                # Insert new
                conn.execute(
                    "INSERT INTO long_term_patterns (pattern_id, description, regime, "
                    "occurrence_count, avg_outcome, confidence, feature_signature, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        pattern.pattern_id,
                        pattern.description,
                        pattern.regime,
                        pattern.occurrence_count,
                        pattern.avg_outcome,
                        pattern.confidence,
                        sig_json,
                        now,
                    ),
                )
        return pattern.pattern_id

    def get_pattern(self, pattern_id: str) -> MarketPattern | None:
        """Get a specific pattern by ID."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM long_term_patterns WHERE pattern_id = ?", (pattern_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_pattern(row)

    def query_by_regime(self, regime: str, limit: int = 10) -> list[MarketPattern]:
        """Get patterns matching a specific regime."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM long_term_patterns WHERE regime = ? "
                "ORDER BY confidence DESC, occurrence_count DESC LIMIT ?",
                (regime, limit),
            ).fetchall()
            return [self._row_to_pattern(r) for r in rows]

    def query_all_patterns(self, limit: int = 50) -> list[MarketPattern]:
        """Get all patterns ordered by confidence."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM long_term_patterns ORDER BY confidence DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_pattern(r) for r in rows]

    @property
    def pattern_count(self) -> int:
        with sqlite3.connect(str(self._db_path)) as conn:
            return conn.execute("SELECT COUNT(*) FROM long_term_patterns").fetchone()[0]

    # === Blacklist ===

    def add_blacklist(self, condition: BlacklistCondition) -> str:
        """Add a blacklist condition."""
        if not condition.condition_id:
            condition.condition_id = str(uuid.uuid4())[:8]

        sig_json = json.dumps(condition.feature_signature)
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO blacklist_conditions "
                "(condition_id, description, feature_signature, avg_loss, occurrence_count, active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    condition.condition_id,
                    condition.description,
                    sig_json,
                    condition.avg_loss,
                    condition.occurrence_count,
                    int(condition.active),
                ),
            )
        return condition.condition_id

    def get_blacklist(self, active_only: bool = True) -> list[BlacklistCondition]:
        """Get blacklist conditions."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM blacklist_conditions"
            if active_only:
                query += " WHERE active = 1"
            rows = conn.execute(query).fetchall()
            return [self._row_to_blacklist(r) for r in rows]

    @property
    def blacklist_count(self) -> int:
        with sqlite3.connect(str(self._db_path)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM blacklist_conditions WHERE active = 1"
            ).fetchone()[0]

    # === Consolidation ===

    def consolidate(self, stm_items: list[MemoryItem]) -> int:
        """
        Consolidate STM items into LTM patterns.
        Groups by regime, computes avg outcome, creates/updates patterns.
        Returns number of patterns created/updated.
        """
        if not stm_items:
            return 0

        # Group trades by regime
        regime_groups: dict[str, list[MemoryItem]] = {}
        for item in stm_items:
            if item.category != "trade":
                continue
            regime = item.data.get("regime", "unknown")
            regime_groups.setdefault(regime, []).append(item)

        count = 0
        for regime, items in regime_groups.items():
            outcomes = [item.data.get("pnl_pct", 0) for item in items]
            avg_out = sum(outcomes) / len(outcomes) if outcomes else 0.0
            confidence = min(len(items) / 10, 1.0)  # more occurrences = higher confidence

            pattern = MarketPattern(
                description=f"Trade pattern in {regime} regime ({len(items)} trades)",
                regime=regime,
                occurrence_count=len(items),
                avg_outcome=avg_out,
                confidence=confidence,
            )
            self.add_pattern(pattern)
            count += 1

            # If avg outcome is very negative, add to blacklist
            if avg_out < -0.01 and len(items) >= 3:
                bl = BlacklistCondition(
                    description=f"Losing pattern in {regime}: avg={avg_out:.4f}",
                    avg_loss=abs(avg_out),
                    occurrence_count=len(items),
                )
                self.add_blacklist(bl)
                logger.debug(
                    f"LTM blacklist: regime={regime}, avg_loss={abs(avg_out):.4f}, n={len(items)}"
                )

        logger.debug(f"LTM consolidation: {count} patterns from {len(stm_items)} STM items")
        return count

    # === Helpers ===

    def _row_to_pattern(self, row) -> MarketPattern:
        return MarketPattern(
            pattern_id=row["pattern_id"],
            description=row["description"],
            regime=row["regime"],
            occurrence_count=row["occurrence_count"],
            avg_outcome=row["avg_outcome"],
            confidence=row["confidence"],
            feature_signature=json.loads(row["feature_signature"]),
            last_seen=datetime.fromisoformat(row["last_seen"]),
        )

    def _row_to_blacklist(self, row) -> BlacklistCondition:
        return BlacklistCondition(
            condition_id=row["condition_id"],
            description=row["description"],
            feature_signature=json.loads(row["feature_signature"]),
            avg_loss=row["avg_loss"],
            occurrence_count=row["occurrence_count"],
            active=bool(row["active"]),
        )
