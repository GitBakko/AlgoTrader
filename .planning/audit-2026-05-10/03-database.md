# Database Layer Audit — 2026-05-10

**Files reviewed:** `backend/src/database/` (all), `backend/alembic/`, repos, backup_manager.

---

## CRITICAL

### C1 — `BaseRepository.update(position_db)` wrong-signature call crashes PAPER-mode close
`backend/src/execution/execution_engine.py:394` + `backend/src/database/repository.py:79`

**What**: `BaseRepository.update(self, id: int, values: dict)` requires two args. Call passes `Position` object as first arg, no `values` → `TypeError: update() missing 1 required positional argument: 'values'`. Caught by exception handler, logs "Database close update failed", position stays OPEN in DB.

**Why it matters**: PAPER-mode close path crashes on every API-triggered close. Ghost positions accumulate, causing stale OPEN rows on restart.

**Fix**: Add `save(position)` method calling `session.flush()`, OR replace `update()` call with explicit `await self.session.flush()`.

---

### C2 — `backup_manager.cleanup_old_backups()` tz-naive vs tz-aware comparison TypeError
`backend/src/database/backup/backup_manager.py:178, 183`

**What**: `cutoff_date = datetime.now(UTC) - timedelta(...)` (tz-aware). `mtime = datetime.fromtimestamp(stat.st_mtime)` (naive). Comparison raises TypeError → caught by try/except → "Backup cleanup failed" → returns 0 → backups accumulate forever.

**Fix**: `mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)`.

---

### C3 — `alembic/env.py` empty `MetaData()` — autogenerate produces DROP ALL migration
`backend/src/database/models.py:23` + `backend/alembic/env.py:37`

**What**: `models.py` declares `metadata = MetaData()` (empty). All ORM models register in `SQLModel.metadata`. Alembic uses the empty `metadata` as `target_metadata`. Running `alembic revision --autogenerate` generates a destructive "drop all tables" migration.

**Fix**: `metadata = SQLModel.metadata` in `models.py`.

---

## HIGH

### H1 — `BaseRepository.count()` full table scan
`backend/src/database/repository.py:117-118`

**What**: `select(self.model)` then `len(list(...all()))`. Loads entire table to count rows.

**Fix**: `select(func.count()).select_from(self.model)`.

---

### H2 — `close_reason != "UNRECONCILED"` silently drops NULL rows from performance stats
`backend/src/database/repositories/position_repository.py:147, 400, 486`

**What**: PostgreSQL `NULL <> 'UNRECONCILED'` evaluates to NULL (not TRUE). Rows with NULL `close_reason` (legacy or bugged) silently excluded from stats.

**Fix**: `(close_reason != "UNRECONCILED") | close_reason.is_(None)`.

---

## MEDIUM

### M1 — `TrailingStopRepository.bulk_delete` — N sequential SELECT+DELETE
`backend/src/database/repositories/trailing_stop_repository.py:131-145`

**Fix**: Single `DELETE WHERE deal_id = ANY(:ids)`.

---

### M2 — Missing index for dealId-rotation fallback query
`backend/src/database/repositories/position_repository.py:73-88`

**What**: Query by `(epic, status=OPEN, direction, entry_price ± tol)`. Index exists on `(epic, status)` but not `entry_price`. Range filter scans all OPEN positions for that epic. Acceptable now (<5 positions/epic) but degrades.

**Fix**: Add index on `(epic, status, entry_price)` in new migration.

---

### M3 — `trade_journal_note_repository.delete_note` missing flush()
`backend/src/database/repositories/trade_journal_note_repository.py:38-43`

**What**: `session.delete(existing)` without flush. Same-session re-query sees stale row.

**Fix**: `await self.session.flush()` after delete.

---

### M4 — `SwapDailySnapshot.id` is `Integer` (32-bit), other tables use `BigInteger`
`backend/src/database/models.py:585`

**What**: One row per epic per day, ~7600/year. No near-term overflow. Inconsistent convention.

---

## Coverage Gaps

- No tests for concurrent CLOSE writes verifying idempotency
- `execution_engine._persist_close_to_db` not exercised in tests
- Migration rollback paths untested (e7a9b1c2d3f4 truncates VARCHAR)
- `PendingCloseRepository` no integration test for `first_seen` preservation
- `backup_manager.cleanup_old_backups()` tz-naive bug untested
- `BaseRepository.count()` perf untested

---

## Summary

| Pri | ID | Location | Issue |
|-----|-----|----------|-------|
| CRITICAL | C1 | execution_engine.py:394 | `update(position_db)` wrong signature → PAPER close crash |
| CRITICAL | C2 | backup_manager.py:178 | tz-naive backup cleanup permanently broken |
| CRITICAL | C3 | models.py:23 | Empty MetaData → autogenerate produces DROP ALL |
| HIGH | H1 | repository.py:117 | count() full table scan |
| HIGH | H2 | position_repository.py:147 | `!=` NULL-unsafe drops perf rows |
| MEDIUM | M1-M4 | various | bulk_delete inefficient, missing index, etc. |
