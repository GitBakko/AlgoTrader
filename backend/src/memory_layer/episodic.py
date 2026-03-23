# MANTIS-EVOLUTION: Episodic Memory
"""Episodic memory: high-impact events that never decay."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from loguru import logger

from src.memory_layer.schemas import (
    Episode,
    MemoryConfig,
    TradeOutcome,
    Warning,
)


class MantisEpisodicMemory:
    """
    Episodic memory: stores high-impact memorable events.

    Episodes are created when:
    - Trade has exceptional P&L (top/bottom 5%)
    - Flash crash / pump detected
    - Extreme Fear&Greed (< 15 or > 85)
    - High-confidence signal resulted in loss

    Episodes NEVER decay. They serve as "lessons learned".
    """

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig()
        self._db_path = Path(self.config.db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize episodes table."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT UNIQUE NOT NULL,
                    epic TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    context_embedding TEXT NOT NULL DEFAULT '[]',
                    outcome_json TEXT,
                    significance REAL NOT NULL DEFAULT 0.0,
                    lesson TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_episodes_epic ON episodes(epic);
                CREATE INDEX IF NOT EXISTS idx_episodes_significance ON episodes(significance);
            """)

    def record_episode(
        self,
        description: str,
        significance: float,
        epic: str = "",
        outcome: TradeOutcome | None = None,
        context_embedding: list[float] | None = None,
        lesson: str = "",
    ) -> str | None:
        """
        Record an episode if significance >= threshold.
        Returns episode_id or None if below threshold.
        """
        if significance < self.config.episodic_significance_threshold:
            return None

        episode_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc)

        outcome_json = outcome.model_dump_json() if outcome else None
        embedding_json = json.dumps(context_embedding or [])

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO episodes (episode_id, epic, description, context_embedding, "
                "outcome_json, significance, lesson, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    episode_id,
                    epic,
                    description,
                    embedding_json,
                    outcome_json,
                    significance,
                    lesson,
                    now.isoformat(),
                ),
            )

        logger.info(f"Episode recorded: {episode_id} ({description[:50]})")
        return episode_id

    def get_episode(self, episode_id: str) -> Episode | None:
        """Get specific episode by ID."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_episode(row)

    def get_all_episodes(self, limit: int = 50) -> list[Episode]:
        """Get all episodes ordered by significance desc."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM episodes ORDER BY significance DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_episode(r) for r in rows]

    def get_by_epic(self, epic: str, limit: int = 10) -> list[Episode]:
        """Get episodes for a specific epic."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM episodes WHERE epic = ? ORDER BY significance DESC LIMIT ?",
                (epic, limit),
            ).fetchall()
            return [self._row_to_episode(r) for r in rows]

    def recall_similar(
        self,
        context_embedding: list[float],
        top_k: int = 3,
    ) -> list[Episode]:
        """
        Find episodes with most similar context embedding.
        Uses cosine similarity.
        """
        if not context_embedding:
            return []

        all_episodes = self.get_all_episodes(limit=100)
        if not all_episodes:
            return []

        query_vec = np.array(context_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm < 1e-8:
            return []

        scored: list[tuple[float, Episode]] = []
        for ep in all_episodes:
            if not ep.context_embedding:
                continue
            ep_vec = np.array(ep.context_embedding, dtype=np.float32)
            ep_norm = np.linalg.norm(ep_vec)
            if ep_norm < 1e-8:
                continue
            similarity = float(np.dot(query_vec, ep_vec) / (query_norm * ep_norm))
            scored.append((similarity, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:top_k]]

    def get_warnings(
        self,
        context_embedding: list[float],
        similarity_threshold: float = 0.7,
    ) -> list[Warning]:
        """
        Generate warnings from episodes with negative outcomes similar to current context.
        """
        if not context_embedding:
            return []

        similar = self.recall_similar(context_embedding, top_k=10)
        warnings: list[Warning] = []

        query_vec = np.array(context_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm < 1e-8:
            return []

        for ep in similar:
            # Only warn about negative episodes
            if ep.outcome is None or ep.outcome.pnl_pct >= 0:
                continue

            if not ep.context_embedding:
                continue

            ep_vec = np.array(ep.context_embedding, dtype=np.float32)
            ep_norm = np.linalg.norm(ep_vec)
            if ep_norm < 1e-8:
                continue

            sim = float(np.dot(query_vec, ep_vec) / (query_norm * ep_norm))
            if sim >= similarity_threshold:
                action = "skip" if sim > 0.9 else "reduce_size"
                warnings.append(
                    Warning(
                        episode_id=ep.episode_id,
                        similarity=sim,
                        description=ep.description,
                        lesson=ep.lesson,
                        recommended_action=action,
                    )
                )

        return warnings

    @property
    def episode_count(self) -> int:
        with sqlite3.connect(str(self._db_path)) as conn:
            return conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]

    def _row_to_episode(self, row) -> Episode:
        outcome = None
        if row["outcome_json"]:
            outcome = TradeOutcome.model_validate_json(row["outcome_json"])
        return Episode(
            episode_id=row["episode_id"],
            epic=row["epic"],
            description=row["description"],
            context_embedding=json.loads(row["context_embedding"]),
            outcome=outcome,
            significance=row["significance"],
            lesson=row["lesson"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )
