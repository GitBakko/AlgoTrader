"""
Backend health sentinel.

Periodic in-process watchdog that detects "soft hangs" the Python runtime
itself cannot crash on:
  * `paper_loop` not iterating for >> the candle resolution it operates on
  * Hourly candle refresh writing 0 candles for >= N consecutive ticks
  * `SessionManager` keep-alive ping silent for > N minutes
  * Broker WS price stream stuck on the reconnect-attempts ceiling

On detection the sentinel logs CRITICAL and fires an alert through the
already-configured AlertManager (in-app + telegram + slack + ...). It does
NOT auto-restart anything in this version — restart policy belongs to an
external supervisor (Sprint C) so a deterministic bug cannot flap-restart
us forever. The sentinel is alert-only on purpose.

Wired up from `src.api.main` lifespan after both `paper_loop` and
`data_scheduler` are constructed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

from src.monitoring.alerting.schemas import Alert, AlertSeverity, AlertType

if TYPE_CHECKING:
    from src.broker.client import CapitalComClient
    from src.data.scheduler import DataScheduler
    from src.monitoring.alerting.alert_manager import AlertManager
    from src.trading.paper_loop import PaperTradingLoop


# Per-resolution cap on "time since last loop iteration" before we shout.
# A 4h-resolution loop should iterate at least once per ~4h+grace; missing
# two consecutive bars (8h+) is the sentinel threshold per the candle-ingest
# debug RCA (see docs/handoff/candle-ingest-rca.md if you happen to find it).
_RESOLUTION_TO_STALL_THRESHOLD: dict[str, timedelta] = {
    "1min": timedelta(minutes=10),
    "5min": timedelta(minutes=30),
    "15min": timedelta(hours=1),
    "30min": timedelta(hours=2),
    "1h": timedelta(hours=3),
    "4h": timedelta(hours=9),
    "1d": timedelta(days=2, hours=12),
}

# Keep-alive ping should fire every 5 minutes; >7min silent means the ping
# task is dying without crashing.
_PING_SILENCE_THRESHOLD = timedelta(minutes=7)

# Hourly refresh writes 0 candles when every epic is empty in the broker's
# response. One zero-tick is benign (mid-bar window on illiquid epic);
# two consecutive zero-ticks is the actual ingest-dead signal.
_REFRESH_DEAD_CONSECUTIVE = 2


@dataclass
class _SentinelState:
    """Rolling window state, used to detect 'stuck' conditions across ticks."""

    last_iteration_count_seen: int = 0
    last_iteration_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    consecutive_zero_hourly_refreshes: int = 0
    last_hourly_at_seen: datetime | None = None
    # Tracks which alerts are currently "firing" so we don't spam every tick.
    firing: set[str] = field(default_factory=set)


class BackendHealthSentinel:
    """In-process watchdog. Alert-only (no restarts here)."""

    def __init__(
        self,
        *,
        paper_loop: PaperTradingLoop | None,
        data_scheduler: DataScheduler | None,
        broker_client: CapitalComClient | None,
        alert_manager: AlertManager | None,
        check_interval_seconds: int = 300,
    ):
        self.paper_loop = paper_loop
        self.data_scheduler = data_scheduler
        self.broker_client = broker_client
        self.alert_manager = alert_manager
        self.check_interval_seconds = check_interval_seconds

        self._state = _SentinelState()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Launch the periodic check task."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "🩺 Backend health sentinel started "
            f"(check every {self.check_interval_seconds}s)"
        )

    async def stop(self) -> None:
        """Cancel the check task. Safe to call repeatedly."""
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _run_loop(self) -> None:
        # First check after a short warm-up so paper_loop has a chance to
        # tick at least once before we judge it.
        await asyncio.sleep(min(60, self.check_interval_seconds))
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                logger.info("Backend health sentinel cancelled")
                raise
            except Exception as exc:
                logger.exception(f"Sentinel tick raised: {exc}")
            await asyncio.sleep(self.check_interval_seconds)

    async def run_once(self) -> None:
        """Single check cycle. Public so tests can drive it deterministically."""
        now = datetime.now(UTC)
        await self._check_loop_progress(now)
        await self._check_hourly_refresh()
        await self._check_ping_heartbeat(now)

    # ── Individual checks ───────────────────────────────────────────

    async def _check_loop_progress(self, now: datetime) -> None:
        loop = self.paper_loop
        if loop is None or not getattr(loop, "is_running", False):
            # Loop intentionally stopped — clear any stuck flag and bail.
            self._clear("loop_stalled")
            return

        iter_count = getattr(loop, "_iteration_count", 0)
        resolution = getattr(loop, "_candle_resolution", "1h")
        threshold = _RESOLUTION_TO_STALL_THRESHOLD.get(resolution, timedelta(hours=4))

        if iter_count != self._state.last_iteration_count_seen:
            # Loop made progress since last check — refresh the marker.
            self._state.last_iteration_count_seen = iter_count
            self._state.last_iteration_seen_at = now
            self._clear("loop_stalled")
            return

        # No progress since last check — see if we've crossed the threshold.
        elapsed = now - self._state.last_iteration_seen_at
        if elapsed < threshold:
            return

        await self._fire_once(
            tag="loop_stalled",
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.SYSTEM_ERROR,
            title="Paper trading loop stalled",
            message=(
                f"No iteration for {elapsed.total_seconds() / 3600:.1f}h on a "
                f"{resolution} candle resolution (threshold "
                f"{threshold.total_seconds() / 3600:.1f}h). Last iteration "
                f"#{iter_count}; last_run={loop.last_run}."
            ),
            details={
                "iteration_count": iter_count,
                "candle_resolution": resolution,
                "elapsed_seconds": elapsed.total_seconds(),
                "threshold_seconds": threshold.total_seconds(),
                "last_run": str(loop.last_run) if loop.last_run else None,
            },
        )

    async def _check_hourly_refresh(self) -> None:
        sched = self.data_scheduler
        if sched is None:
            return

        last_at: datetime | None = getattr(sched, "_last_hourly_at", None)
        last_count: int = int(getattr(sched, "_last_hourly_count", 0) or 0)

        if last_at is None:
            # Scheduler hasn't ticked yet — too early to judge.
            return

        # Detect a fresh tick: timestamp moved forward since we last looked.
        moved = (
            self._state.last_hourly_at_seen is None
            or last_at > self._state.last_hourly_at_seen
        )
        if not moved:
            return  # No new run since last sentinel tick — nothing to record.

        self._state.last_hourly_at_seen = last_at
        if last_count == 0:
            self._state.consecutive_zero_hourly_refreshes += 1
        else:
            self._state.consecutive_zero_hourly_refreshes = 0
            self._clear("hourly_refresh_dead")
            return

        if self._state.consecutive_zero_hourly_refreshes >= _REFRESH_DEAD_CONSECUTIVE:
            await self._fire_once(
                tag="hourly_refresh_dead",
                severity=AlertSeverity.CRITICAL,
                alert_type=AlertType.SYSTEM_ERROR,
                title="Hourly candle refresh writing 0 candles",
                message=(
                    f"{self._state.consecutive_zero_hourly_refreshes} consecutive "
                    f"hourly refresh runs wrote 0 candles. Capital.com /history/prices "
                    f"is likely returning errors for every epic — investigate broker "
                    f"connectivity / session / rate-limit. Last run: {last_at}."
                ),
                details={
                    "consecutive_zero_runs": self._state.consecutive_zero_hourly_refreshes,
                    "last_run_at": last_at.isoformat(),
                },
            )

    async def _check_ping_heartbeat(self, now: datetime) -> None:
        client = self.broker_client
        if client is None or client.session is None:
            return

        last_ping: datetime | None = getattr(
            client.session, "last_successful_ping_at", None
        )
        if last_ping is None:
            # No ping ever — still in warm-up window.
            return

        elapsed = now - last_ping
        if elapsed < _PING_SILENCE_THRESHOLD:
            self._clear("ping_silent")
            return

        await self._fire_once(
            tag="ping_silent",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.BROKER_DISCONNECTED,
            title="Capital.com keep-alive ping silent",
            message=(
                f"No successful broker ping for {elapsed.total_seconds() / 60:.1f} min "
                f"(threshold {_PING_SILENCE_THRESHOLD.total_seconds() / 60:.0f} min). "
                f"Session may have expired without auto-refresh."
            ),
            details={
                "elapsed_minutes": elapsed.total_seconds() / 60,
                "last_successful_ping_at": last_ping.isoformat(),
            },
        )

    # ── Alert plumbing ──────────────────────────────────────────────

    async def _fire_once(
        self,
        *,
        tag: str,
        severity: AlertSeverity,
        alert_type: AlertType,
        title: str,
        message: str,
        details: dict[str, object],
    ) -> None:
        """Fire `tag` only if it's not already firing — avoids per-tick spam."""
        if tag in self._state.firing:
            return
        self._state.firing.add(tag)

        # Always log CRITICAL/WARNING to the central error stream so the log
        # tail tells the same story as the alert channels.
        log_fn = logger.critical if severity == AlertSeverity.CRITICAL else logger.warning
        log_fn(f"🩺 SENTINEL [{tag}] {title} — {message}")

        if self.alert_manager is None:
            return
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            details=details,
        )
        try:
            await self.alert_manager.send_alert(alert)
        except Exception as exc:
            logger.error(f"Sentinel alert dispatch failed: {exc}")

    def _clear(self, tag: str) -> None:
        if tag in self._state.firing:
            self._state.firing.discard(tag)
            logger.info(f"🩺 SENTINEL [{tag}] cleared — condition resolved")
