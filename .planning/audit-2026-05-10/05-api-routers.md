# API Routers + Auth + WS Audit — 2026-05-10

**Files reviewed:** `backend/src/api/main.py`, `routers/*` (all), `websocket.py`, `auth/`, `security/`, tests.

---

## CRITICAL

### C1 — All trading/operations endpoints UNAUTHENTICATED — auth bypass on entire control surface
**Multiple files** — only `auth.py` uses `get_current_user`.

**What**: `POST /api/trading/start|stop|emergency-stop|reset-circuit-breakers|reset-risk-state`, `POST /api/models/train/{epic}`, `POST /api/models/retrain-all`, `POST /api/positions/close/{deal_id}`, `PUT /api/positions/{deal_id}/stops`, `PUT /api/strategy/risk-limits|config` — **all** accept requests with NO authentication. `require_permission`/`require_role` exist in `src/auth/dependencies.py` but never applied outside auth tests.

**Why it matters**: Any network-reachable client can stop trading, fire emergency-stop (closes ALL real broker positions), reset CBs, retrain models, close positions, modify risk limits. Full financial compromise via unauthenticated POST.

**Fix**: Add `current_user: Annotated[User, Depends(get_current_user)]` to every state-changing endpoint. For LIVE deploy: `dependencies=[Depends(require_permission("trading","execute"))]`.

---

### C2 — `POST /api/auth/register` accepts `role_name` from request — anyone can self-create ADMIN account
`backend/src/api/routers/auth.py:152-229`

**What**: Endpoint unauthenticated, accepts `role_name` string from body. Only gate is 5/hour IP rate limit. POST with `"role_name": "ADMIN"` returns full-admin account.

**Why it matters**: Privilege escalation to ADMIN without any prior credentials.

**Fix**: Hard-code new-user role to VIEWER ignoring `role_name`, OR gate behind `Depends(require_role("ADMIN"))`, OR feature-flag `OPEN_REGISTRATION`.

---

### C3 — `GET /api/auth/avatar/{user_id}` unauthenticated, no path-traversal containment
`backend/src/api/routers/auth.py:487-522`

**What**: Reads `avatar_storage_path` from DB, calls `Path(storage_path).exists()`, serves via `FileResponse`. No auth. No verify path is under `AVATAR_STORAGE_DIR`.

**Why it matters**: (1) Unauth enumeration of user avatars. (2) If DB value escapes `data/avatars/` (via prior bug or manual edit), arbitrary file served from filesystem.

**Fix**: Add `current_user` dependency. Validate `Path(storage_path).resolve().is_relative_to(AVATAR_STORAGE_DIR.resolve())` before serving.

---

## HIGH

### H1 — Local `_error()` ignores `status` param — always returns HTTP 200
`backend/src/api/routers/agents.py:26` + `backend/src/api/routers/vision.py:30`

**What**: Returns plain dict, not `JSONResponse`. FastAPI serializes as 200 regardless of `status` arg. `_error("...", 403)` returns 200.

**Fix**: Replace with canonical `error_response(msg, status_code)` from `src.api.schemas`.

---

### H2 — `success_response(..., status_code=503)` raises TypeError → 500 instead of 503
`backend/src/api/routers/models.py:520-522`

**What**: `success_response(data) -> dict` accepts only one arg. `status_code=503` keyword raises TypeError, caught by global handler → 500.

**Fix**: `error_response("Training orchestrator non disponibile", 503)`.

---

### H3 — Signal handler + lifespan double-close broker WS and DB
`backend/src/api/main.py:607-670` vs `546-603`

**What**: SIGTERM handler runs `shutdown_handler` (disconnect WS + close broker + close DB) async task. Lifespan yield then runs same three calls. Double-close can raise RuntimeError mid-shutdown, leaving background tasks dangling.

**Fix**: Signal handler only sets `is_shutting_down=True`. All cleanup in lifespan.

---

### H4 — `GET /api/positions/closed` double-fetches up to 10K rows for aggregates per request
`backend/src/api/routers/positions.py:111-118`

**What**: After paginated query, second `limit=10000` query for aggregates. No caching. Per-page-load DoS vector against Postgres.

**Fix**: Single query with `SUM/COUNT/AVG`.

---

### H5 — `ConnectionManager.broadcast` not asyncio-safe — concurrent mutations during iteration
`backend/src/api/websocket.py:52-67`

**What**: Iterates `self._connections[channel]`, then rebuilds list. Cooperative scheduler can interleave `connect()` between iteration and rebuild → lost client.

**Fix**: Snapshot at start: `connections = list(self._connections.get(channel, []))`.

---

## MEDIUM

### M1 — Refresh token race: concurrent `/refresh` with same token can issue two valid new refresh tokens
`backend/src/api/routers/auth.py:307-392`

**What**: Per-request atomic but no row-level lock. asyncpg READ COMMITTED isolation → two concurrent refresh calls both pass `is_revoked == False` check before either commits.

**Fix**: `SELECT FOR UPDATE` on `RefreshToken` row, OR DB unique constraint on `(user_id, is_revoked=False)`.

---

### M2 — JSONB `features` content propagated to API without sanitization
`backend/src/api/routers/trading.py:159-178`

**What**: Not SQL injection (parameterized) but stored XSS vector if Telegram/external signals ever write `features`. Angular auto-escapes mitigates but document assumption.

---

### M3 — Empty/error responses returned with `success_response` HTTP 200 — indistinguishable from valid empty data
`backend/src/api/schemas.py:14-16`

**Example**: `/api/trading/pnl-history` with no DB returns 200 + empty data, not 503.

**Fix**: Use `error_response` for degraded service paths.

---

### M4 — `Path("data/historical")` relative to CWD, not module location
`backend/src/api/routers/analytics.py:45`

**Fix**: `Path(__file__).resolve().parent.parent.parent.parent / "data" / "historical"`.

---

### M5 — Avatar `media_type="image/jpeg"` hardcoded
`backend/src/api/routers/auth.py:519`

**Fix**: `mimetypes.guess_type(file_path)` or auto-detect.

---

## LOW

### L1 — `subprocess.Popen(stdout=log_file.open("w"))` file handle never closed
`backend/src/api/routers/models.py:492-498`

### L2 — WS endpoints accept arbitrary text frames, no size limit
`backend/src/api/websocket.py:481-542`

**Fix**: `if len(data) > 64: continue`.

### L3 — `GET /api/system/events` permanently stubbed returns `[]`
`backend/src/api/routers/system.py:73-79`

**Fix**: Implement OR return 501.

---

## Coverage Gaps

1. NO test file for `auth.py` — login fail, register dup, refresh, logout, avatar all uncovered
2. NO test for unauthenticated access to protected routes (because routes don't require auth — see C1)
3. NO test for `_error()` HTTP status (would catch H1)
4. NO test for concurrent refresh token race (M1)
5. NO test for `success_response(status_code=)` TypeError (H2)
6. `test_trading_emergency.py` doesn't test auth requirement

---

## Summary

| Pri | ID | Location | Issue |
|-----|-----|----------|-------|
| **CRITICAL** | C1 | All routers | UNAUTHENTICATED trading endpoints — full bypass |
| **CRITICAL** | C2 | auth.py:152 | Self-register ADMIN privilege escalation |
| **CRITICAL** | C3 | auth.py:487 | Avatar serve no auth + no path containment |
| HIGH | H1 | agents.py:26, vision.py:30 | `_error()` returns 200 not status |
| HIGH | H2 | models.py:520 | `success_response(status_code=)` → 500 |
| HIGH | H3 | main.py:607 | Double-close shutdown race |
| HIGH | H4 | positions.py:111 | 10K-row aggregate per page DoS |
| HIGH | H5 | websocket.py:52 | broadcast() concurrent mutation |
| MEDIUM | M1-M5 | various | refresh race, relative path, MIME, etc. |
| LOW | L1-L3 | various | FD leak, WS size, stub endpoint |
