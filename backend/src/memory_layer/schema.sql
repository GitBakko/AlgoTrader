-- MANTIS-EVOLUTION: Memory Layer SQLite Schema
-- Creates all tables for the Long-Term Memory (LTM) and Episodic Memory layers.
-- Short-Term Memory (STM) is in-memory only (no DB table needed).
--
-- Feature signatures and embeddings are stored as JSON arrays of floats.
-- Datetimes are stored as ISO-8601 TEXT (UTC).

CREATE TABLE IF NOT EXISTS long_term_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    regime TEXT NOT NULL DEFAULT '',
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    avg_outcome REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 0.0,
    feature_signature TEXT NOT NULL DEFAULT '[]',  -- JSON array of floats
    last_seen TEXT NOT NULL,                        -- ISO datetime (UTC)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT UNIQUE NOT NULL,
    epic TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    context_embedding TEXT NOT NULL DEFAULT '[]',   -- JSON array of floats
    outcome_json TEXT,                              -- JSON-serialized TradeOutcome (nullable)
    significance REAL NOT NULL DEFAULT 0.0,
    lesson TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,                        -- ISO datetime (UTC)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS blacklist_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    feature_signature TEXT NOT NULL DEFAULT '[]',   -- JSON array of floats
    avg_loss REAL NOT NULL DEFAULT 0.0,
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,              -- SQLite boolean: 1=True, 0=False
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_patterns_regime ON long_term_patterns(regime);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON long_term_patterns(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_epic ON episodes(epic);
CREATE INDEX IF NOT EXISTS idx_episodes_significance ON episodes(significance DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_blacklist_active ON blacklist_conditions(active);
