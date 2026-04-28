import { ChangeDetectionStrategy, Component, computed, effect, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { CockpitHeaderComponent, type CockpitMode, type CockpitState } from '../../shared/components/cockpit-header/cockpit-header.component';
import { TradingService } from '../../core/services/trading.service';
import { SignalAuditService } from '../../core/services/signal-audit.service';
import { ToastService } from '../../shared/services/toast.service';
import { ConfirmDialogService } from '../../shared/services/confirm-dialog.service';
import type {
  BotVitals,
  KpiStrip,
  ModelsHealth,
  ModelsHealthMeta,
  PaperTradingPosition,
  RiskState,
} from '../../core/models/paper-trading';
import { BotVitalsPanelComponent } from './components/bot-vitals-panel/bot-vitals-panel.component';
import { RiskGaugeStackComponent } from './components/risk-gauge-stack/risk-gauge-stack.component';
import { ModelsHealthPanelComponent } from './components/models-health-panel/models-health-panel.component';
import { KpiStripCompactComponent } from './components/kpi-strip-compact/kpi-strip-compact.component';
import { ActivePositionsCockpitComponent } from './components/active-positions-cockpit/active-positions-cockpit.component';
import { PositionDetailDrawerComponent } from './components/position-detail-drawer/position-detail-drawer.component';
import { SignalsHeatmapComponent, type HeatmapCell } from './components/signals-heatmap/signals-heatmap.component';
import { LiveFeedTimelineComponent } from './components/live-feed-timeline/live-feed-timeline.component';
import type { FeedEvent } from '../../core/models';
import { WebSocketService } from '../../core/services/websocket.service';
import type { PaperPosition } from '../../core/models';
import { epicColor } from '../../shared/constants/epic-colors';

const CIRCUIT_BREAKER_TOTAL = 6;
const DEFAULT_DD_GATE_PCT = 20;
/** Polling cadences (ms). The backend captures snapshots every 60s, so
 *  we refresh the KPI history on the same beat. Per-position charts
 *  refresh more aggressively to feel live while a position is open. */
const PNL_HISTORY_REFRESH_MS = 60_000;
const POSITION_HISTORY_REFRESH_MS = 30_000;
/** How often the cockpit re-pulls the merged activity feed and the recent
 *  signal history. Tight enough to feel live; gentle enough on Postgres. */
const FEED_REFRESH_MS = 8_000;
const SIGNALS_REFRESH_MS = 12_000;
/** How many historical signal rows we ask the backend for. The heatmap
 *  groups by epic and takes the latest, so we need enough rows to cover
 *  the full 21-asset universe even when one asset dominates the feed. */
const SIGNALS_HISTORY_LIMIT = 300;

/**
 * Paper Trading v2 — cockpit shell.
 *
 * PR 1 · chrome (cockpit-header + 3-col grid + footer).
 * PR 2 · left rail (bot-vitals + risk-gauges + models-health).
 *
 * Source: docs/handoff/paper-trading/HANDOFF.md.
 */
@Component({
  selector: 'app-paper-trading',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    CockpitHeaderComponent,
    BotVitalsPanelComponent,
    RiskGaugeStackComponent,
    ModelsHealthPanelComponent,
    KpiStripCompactComponent,
    ActivePositionsCockpitComponent,
    PositionDetailDrawerComponent,
    SignalsHeatmapComponent,
    LiveFeedTimelineComponent,
  ],
  templateUrl: './paper-trading.component.html',
  styleUrls: ['./paper-trading.component.scss'],
  host: {
    'data-screen-label': '02 Paper Trading',
  },
})
export class PaperTradingComponent implements OnInit, OnDestroy {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  private readonly toast = inject(ToastService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  private readonly signalAudit = inject(SignalAuditService);

  readonly stopBusy = signal(false);
  readonly emergencyBusy = signal(false);

  /** Deal id of the position currently shown in the right-side detail drawer.
   *  Stored as id (not as the object) so the resolved position computed below
   *  always reflects the latest live data without us writing back into the
   *  signal from an effect. `null` keeps the drawer closed. */
  readonly selectedPositionId = signal<string | null>(null);

  /** Wall-clock signal updated every 1s so `lastTickAgo` and dependent
   *  computeds (cockpit-header tick chip, ECG label) re-render every second
   *  even when the 10s polling cycle has not refreshed `paperStatus` yet. */
  readonly tickClock = signal(Date.now());

  readonly status = this.trading.paperStatus;
  readonly overview = this.trading.overview;
  readonly currency = computed<string>(() => this.overview()?.currency ?? 'USD');

  /** Live broker positions surfaced verbatim (no adapter). The heatmap
   *  needs the raw `PaperPosition[]` shape to overlay live state per epic. */
  readonly brokerPositions = this.trading.paperPositions;

  /** Recent signal history (DB-backed) used by the heatmap to compute
   *  "latest signal per epic". Pulled from `/api/signals/`. */
  readonly tradingSignals = this.trading.signals;

  /** Merged activity feed (signals + positions + notifications) used by
   *  the live-feed-timeline. Pulled from `/api/trading/events`. */
  readonly feedEvents = this.trading.feedEvents;

  /** 21-asset universe surfaced by `/trading/status`. The heatmap renders
   *  one fixed cell per epic regardless of how many signals exist. */
  readonly heatmapEpics = computed<readonly string[]>(() => this.status()?.epics ?? []);

  /** True until both signals and feed have produced their first response.
   *  Drives the heatmap and feed skeletons. */
  readonly telemetryLoading = computed<boolean>(
    () => this.tradingSignals().length === 0 && this.feedEvents().length === 0 && this.status() === null,
  );

  /** Real per-position price history sourced from the backend snapshot
   *  endpoint (`/api/trading/positions/{deal_id}/pnl-history`). The
   *  scheduler captures one row every 60s while the position is open. */
  readonly positionHistory = this.trading.positionPnlHistory;

  /** Real KPI sparkline history sourced from the backend snapshot
   *  endpoint (`/api/trading/pnl-history`). */
  readonly paperPnlHistory = this.trading.paperPnlHistory;

  /** Throttled heartbeat from the WS price feed (≥1.5s between beats so
   *  100 ticks/s do not flood the ECG). Combined into `heartbeatNonce`. */
  readonly priceTickPulse = signal(0);
  private lastPriceTickAt = 0;

  /**
   * Composite "fresh data arrived" nonce. Changes whenever the values the
   * cockpit cares about change — paper status, positions, history, throttled
   * WS prices. The bot-vitals panel reads it as a signal input and beats
   * the ECG once per change instead of running an idle CSS scroll loop.
   */
  readonly heartbeatNonce = computed<string>(() => {
    const status = this.trading.paperStatus();
    const positions = this.trading.paperPositions();
    const paperHistory = this.trading.paperPnlHistory();
    const positionHistory = this.trading.positionPnlHistory();
    return [
      status?.iteration_count ?? 0,
      status?.last_run ?? '',
      status?.signal_count ?? 0,
      positions.length,
      paperHistory?.points.length ?? 0,
      Object.keys(positionHistory).length,
      this.priceTickPulse(),
    ].join('|');
  });

  readonly state = computed<CockpitState>(() => {
    const s = this.status();
    if (!s) return 'IDLE';
    if ((s.error_count ?? 0) > 0) return 'ERROR';
    return s.running ? 'RUNNING' : 'IDLE';
  });

  /** True until /trading/status returns its first response. We use it to
   *  swap the KPI strip and the active-positions stack for skeleton
   *  placeholders so the cockpit doesn't flash empty cells on first paint. */
  readonly isInitialLoading = computed<boolean>(() => this.status() === null);

  /** Position currently bound to the detail drawer. Null while the drawer
   *  is closed or after the underlying position is gone from the broker
   *  list (SL hit, TP hit, manual close), which auto-dismisses the drawer. */
  readonly selectedPosition = computed<PaperTradingPosition | null>(() => {
    const id = this.selectedPositionId();
    if (!id) return null;
    return this.positions().find((p) => p.id === id) ?? null;
  });

  readonly mode = computed<CockpitMode>(() => {
    const raw = this.status()?.execution_mode ?? 'DEMO';
    return (raw === 'LIVE' || raw === 'PAPER') ? raw : 'DEMO';
  });

  readonly lastTickAgo = computed<number | null>(() => {
    const iso = this.status()?.last_run;
    if (!iso) return null;
    const ts = Date.parse(iso);
    if (Number.isNaN(ts)) return null;
    return Math.max(0, (this.tickClock() - ts) / 1000);
  });

  /** BotVitals derived from paperStatus. PR2 baseline: rejected/hold not yet
   *  surfaced by /trading/status — fall back to executed split. */
  readonly botVitals = computed<BotVitals>(() => {
    const s = this.status();
    const total = s?.signal_count ?? 0;
    const executed = s?.trade_count ?? 0;
    const rejected = 0;
    const hold = Math.max(0, total - executed - rejected);
    return {
      state: this.state(),
      uptime: formatUptime(s?.uptime_seconds ?? null),
      lastTickAgo: this.lastTickAgo(),
      iterations: s?.iteration_count ?? 0,
      intervalSec: s?.interval_seconds ?? 0,
      errors: s?.error_count ?? 0,
      signals: {
        total,
        executed,
        rejected,
        hold,
        conversion: total > 0 ? executed / total : 0,
      },
    };
  });

  readonly riskState = computed<RiskState>(() => {
    const s = this.status();
    const rs = this.trading.riskStatus();
    const cbRaw = s?.circuit_breakers_tripped ?? {};
    const cbTripped = Array.isArray(cbRaw) ? cbRaw.length : Object.keys(cbRaw).length;
    const equityBelow = s?.equity_curve_below_sma === true;
    const kelly = s?.kelly_stats ?? null;
    // Backend stores current_drawdown_pct as a decimal fraction (0.04 = 4%).
    const ddPct = (rs?.current_drawdown_pct ?? 0) * 100;
    const ddOverThreshold = ddPct >= DEFAULT_DD_GATE_PCT * 0.7;
    return {
      circuitBreakers: {
        status: cbTripped === 0 ? 'OK' : 'WARN',
        tripped: cbTripped,
        total: CIRCUIT_BREAKER_TOTAL,
      },
      equityFilter: {
        status: equityBelow || ddOverThreshold ? 'WARN' : 'OK',
        dd: ddPct,
        threshold: DEFAULT_DD_GATE_PCT,
      },
      kelly: {
        status: kelly?.active ? 'ATTIVO' : 'PAUSED',
        avg: kelly?.total_trades ?? 0,
        win: (kelly?.win_rate ?? 0) * 100,
        fraction: (kelly?.half_kelly ?? kelly?.kelly_fraction ?? 0) * 100,
      },
      tradingStops: {
        status: 'OK',
        count: s?.trailing_stops_tracked ?? 0,
      },
    };
  });

  /** Live PaperTradingPosition list adapted from broker positions + WS ticks. */
  readonly positions = computed<PaperTradingPosition[]>(() => {
    const broker = this.trading.paperPositions();
    const prices = this.ws.prices();
    const histories = this.positionHistory();
    const now = this.tickClock();
    return broker.map((p) => {
      const snapshot = histories[p.deal_id];
      const path = snapshot?.points?.map((pt) => pt.price).filter((v) => Number.isFinite(v)) ?? [];
      return adaptPosition(p, prices[p.epic], path, now);
    });
  });

  /** Sparkline arrays for the KPI strip cells, derived from the real
   *  paper-pnl-snapshots endpoint. Empty when the backend has no rows
   *  yet — the KPI cell renders without a chart in that case. */
  readonly kpiSparkOpen = computed<number[]>(() => {
    const points = this.paperPnlHistory()?.points ?? [];
    return points.map((p) => p.pnl_open).filter((v) => Number.isFinite(v));
  });

  readonly kpiSparkToday = computed<number[]>(() => {
    const points = this.paperPnlHistory()?.points ?? [];
    return points.map((p) => p.pnl_today).filter((v) => Number.isFinite(v));
  });

  readonly kpiStrip = computed<KpiStrip>(() => {
    const positions = this.positions();
    const o = this.overview();
    const s = this.status();
    const rs = this.trading.riskStatus();
    const kelly = s?.kelly_stats ?? null;
    const ddPct = (rs?.current_drawdown_pct ?? 0) * 100;
    const pnlOpen = positions.reduce((sum, p) => sum + p.pnlEur, 0);
    const pnlToday = o?.today_realized_pnl ?? 0;
    const winRate = (kelly?.win_rate ?? o?.win_rate ?? 0) * 100;
    const rrAvg = positions.length
      ? positions.reduce((sum, p) => sum + p.rr, 0) / positions.length
      : 0;
    return {
      pnlOpen,
      pnlToday,
      openCount: positions.length,
      winRate,
      signalsTotal: s?.signal_count ?? 0,
      rr: rrAvg,
      ddLive: ddPct,
      ddGate: DEFAULT_DD_GATE_PCT,
      sparkOpen: this.kpiSparkOpen(),
      sparkToday: this.kpiSparkToday(),
    };
  });

  readonly modelsHealth = computed<ModelsHealth>(() => {
    const s = this.status();
    const epics = s?.epics ?? [];
    const loaded = s?.models_loaded ?? {};
    const loadedKeys = Object.keys(loaded);
    const primary = loadedKeys.length > 0 ? loaded[loadedKeys[0]] : null;
    const meta: ModelsHealthMeta | undefined = primary
      ? {
          features: primary.num_features,
          version: primary.version,
          lastTrained: formatTrainedDate(primary.created_at),
        }
      : undefined;
    return {
      loaded: loadedKeys.length,
      total: epics.length,
      perAsset: epics.map((epic) => ({
        epic,
        status: loaded[epic] ? 'ok' : 'missing',
        accent: epicColor(epic),
      })),
      meta,
    };
  });

  constructor() {
    // WS prices reshuffle on every broker tick (potentially many per second).
    // Throttle to one beat every 1.5s so the ECG visual does not become a
    // strobe under heavy market activity.
    effect(() => {
      this.ws.prices();
      const now = Date.now();
      if (now - this.lastPriceTickAt >= 1500) {
        this.lastPriceTickAt = now;
        this.priceTickPulse.set(now);
      }
    });

  }

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private clockTimer: ReturnType<typeof setInterval> | null = null;
  private historyTimer: ReturnType<typeof setInterval> | null = null;
  private positionHistoryTimer: ReturnType<typeof setInterval> | null = null;
  private feedTimer: ReturnType<typeof setInterval> | null = null;
  private signalsTimer: ReturnType<typeof setInterval> | null = null;
  private knownDealIds = new Set<string>();


  ngOnInit(): void {
    this.trading.loadPaperStatus();
    this.trading.loadRiskStatus();
    this.trading.loadOverview();
    this.trading.loadPaperPositions();
    this.trading.loadPaperPnlHistory();
    this.trading.loadSignals(undefined, SIGNALS_HISTORY_LIMIT);
    this.trading.loadFeedEvents();
    this.ws.connectPrices();
    this.pollTimer = setInterval(() => {
      this.trading.loadPaperStatus();
      this.trading.loadRiskStatus();
      this.trading.loadOverview();
      this.trading.loadPaperPositions();
    }, 10_000);
    this.clockTimer = setInterval(() => this.tickClock.set(Date.now()), 1_000);
    this.historyTimer = setInterval(
      () => this.trading.loadPaperPnlHistory(),
      PNL_HISTORY_REFRESH_MS,
    );
    this.positionHistoryTimer = setInterval(
      () => this.refreshPositionHistories(),
      POSITION_HISTORY_REFRESH_MS,
    );
    this.feedTimer = setInterval(() => this.trading.loadFeedEvents(), FEED_REFRESH_MS);
    this.signalsTimer = setInterval(
      () => this.trading.loadSignals(undefined, SIGNALS_HISTORY_LIMIT),
      SIGNALS_REFRESH_MS,
    );
    // Kick the first fetch right after the position list lands so the
    // chart isn't blank for a full 30s.
    queueMicrotask(() => this.refreshPositionHistories());
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.clockTimer) {
      clearInterval(this.clockTimer);
      this.clockTimer = null;
    }
    if (this.historyTimer) {
      clearInterval(this.historyTimer);
      this.historyTimer = null;
    }
    if (this.positionHistoryTimer) {
      clearInterval(this.positionHistoryTimer);
      this.positionHistoryTimer = null;
    }
    if (this.feedTimer) {
      clearInterval(this.feedTimer);
      this.feedTimer = null;
    }
    if (this.signalsTimer) {
      clearInterval(this.signalsTimer);
      this.signalsTimer = null;
    }
  }

  /** Re-fetch per-position P&L history. Called on a timer + every time
   *  a new deal_id appears in the broker positions list, so the chart
   *  starts populating immediately rather than waiting the full poll. */
  private refreshPositionHistories(): void {
    const broker = this.trading.paperPositions();
    const liveIds = new Set<string>();
    for (const p of broker) {
      liveIds.add(p.deal_id);
      this.trading.loadPositionPnlHistory(p.deal_id);
    }
    this.knownDealIds = liveIds;
  }

  async onStop(): Promise<void> {
    if (this.stopBusy()) return;
    const running = this.status()?.running === true;
    const confirmed = await this.confirmDialog.confirm({
      title: running ? 'Stop Paper Trading' : 'Start Paper Trading',
      message: running
        ? 'Vuoi fermare il loop di paper trading? Le posizioni aperte restano sul broker.'
        : 'Avviare il loop di paper trading?',
      confirmText: running ? 'Stop' : 'Start',
      cancelText: 'Annulla',
      color: running ? 'warning' : 'primary',
    });
    if (!confirmed) return;

    this.stopBusy.set(true);
    const action$ = running ? this.trading.stopPaperTrading() : this.trading.startPaperTrading();
    action$.subscribe({
      next: (data) => {
        this.toast.success(data.message);
        this.stopBusy.set(false);
        this.trading.loadPaperStatus();
      },
      error: (err) => {
        this.toast.error(err?.error?.error ?? 'Operazione fallita');
        this.stopBusy.set(false);
      },
    });
  }

  async onClosePosition(p: PaperTradingPosition): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: `Chiudere ${p.ticker}?`,
      message: `Chiusura della posizione ${p.direction} ${p.ticker} al prezzo corrente. Procedere?`,
      confirmText: 'Chiudi',
      cancelText: 'Annulla',
      color: 'danger',
    });
    if (!confirmed) return;

    this.trading.closePosition(p.id).subscribe({
      next: () => {
        this.toast.success(`Posizione ${p.ticker} chiusa`);
        this.trading.loadPaperPositions();
        this.trading.loadPaperStatus();
      },
      error: (err) => {
        this.toast.error(err?.error?.error ?? `Chiusura ${p.ticker} fallita`);
      },
    });
  }

  onPositionDetails(p: PaperTradingPosition): void {
    this.selectedPositionId.set(p.id);
  }

  onDrawerClosed(): void {
    this.selectedPositionId.set(null);
  }

  /** Heatmap click → open the global signal-audit drawer for the cell's
   *  most recent signal on that epic. Re-uses the existing audit logic
   *  rather than introducing a parallel drawer just for the heatmap. */
  onHeatmapCellClick(cell: HeatmapCell): void {
    if (cell.state === 'live') {
      // If the epic has an open position, surface the position drawer instead
      // so the user lands on the live trade context, not the signal that opened it.
      const live = this.trading.paperPositions().find((p) => p.epic === cell.epic);
      if (live) {
        this.selectedPositionId.set(live.deal_id);
        return;
      }
    }
    // Fall back to the global signal-audit drawer (latest by epic).
    if (cell.epic && cell.state !== 'none') {
      this.signalAudit.openLatestByEpic(cell.epic);
    }
  }

  /** Feed-row click → open the signal-audit drawer with the row's reasoning,
   *  pro/contro vote breakdown and ML agreement (HANDOFF §3.8). The feed
   *  row id is prefixed (`signal-{n}`, `pos-open-{n}`, `pos-close-{n}`,
   *  `notif-{n}`); we resolve to the right drawer call from the prefix. */
  onFeedEventClick(event: FeedEvent): void {
    const id = event.id ?? '';
    if (id.startsWith('signal-')) {
      const numeric = Number(id.slice('signal-'.length));
      if (Number.isFinite(numeric) && numeric > 0) {
        this.signalAudit.open(numeric);
        return;
      }
    }
    if (id.startsWith('pos-open-') || id.startsWith('pos-close-')) {
      // `meta` carries the broker deal_id for position-open events; the
      // open-by-deal endpoint walks back to the source signal via the
      // signal_id FK so we can render the same audit panel.
      const dealId = event.meta && id.startsWith('pos-open-') ? event.meta : null;
      if (dealId) {
        this.signalAudit.openByDealId(dealId, event.epic ?? undefined);
        return;
      }
    }
    // Fallback: latest signal by epic. Keeps the click meaningful even for
    // notification rows tied to a specific asset.
    if (event.epic) {
      this.signalAudit.openLatestByEpic(event.epic);
    }
  }

  async onEmergency(): Promise<void> {
    if (this.emergencyBusy()) return;
    const confirmed = await this.confirmDialog.confirm({
      title: 'Emergency Stop',
      message: 'ATTENZIONE: chiude TUTTE le posizioni aperte e ferma il loop. Procedere?',
      confirmText: 'Ferma tutto',
      cancelText: 'Annulla',
      color: 'danger',
    });
    if (!confirmed) return;

    this.emergencyBusy.set(true);
    this.trading.emergencyStop().subscribe({
      next: (data) => {
        this.toast.success(data.message);
        this.emergencyBusy.set(false);
        this.trading.loadPaperStatus();
      },
      error: (err) => {
        this.toast.error(err?.error?.error ?? 'Emergency stop fallito');
        this.emergencyBusy.set(false);
      },
    });
  }
}

function formatUptime(seconds: number | null): string {
  if (!seconds || seconds <= 0) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function adaptPosition(
  p: PaperPosition,
  tick: { bid: number; offer: number } | undefined,
  history: number[],
  nowMs: number,
): PaperTradingPosition {
  const direction = (p.direction === 'BUY' ? 'BUY' : 'SELL') as 'BUY' | 'SELL';
  const current = tick
    ? (direction === 'BUY' ? tick.bid : tick.offer)
    : p.level;
  const stopLoss = p.stop_level ?? p.level;
  const takeProfit = p.profit_level ?? p.level;
  const upl = p.upl;
  const livePnl = upl != null
    ? upl
    : (direction === 'BUY' ? (current - p.level) : (p.level - current)) * p.size;
  const denom = p.level || 1;
  const pnlPct = ((current - p.level) / denom) * 100 * (direction === 'BUY' ? 1 : -1);
  const openedMs = p.opened_at ? Date.parse(p.opened_at) : nowMs;
  const ageSec = Math.max(0, Math.floor((nowMs - openedMs) / 1000));
  const risk = Math.abs(p.level - stopLoss) || 1;
  const reward = Math.abs(takeProfit - p.level);
  const rr = reward / risk;
  const trailing = !!p.trailing_stop_phase && p.trailing_stop_phase !== 'INITIAL';
  // Real history from `position_pnl_snapshots`. Empty until the 60s
  // scheduler has captured at least one row; the chart honours that
  // and shows a "in attesa di tick…" placeholder rather than fabricating
  // a line. The current live price is appended so the chart reads up
  // to the moment of render.
  const pricePath = history.length > 0
    ? [...history, current]
    : [];
  return {
    id: p.deal_id,
    ticker: p.epic,
    direction,
    size: p.size,
    entry: p.level,
    stopLoss,
    takeProfit,
    current,
    pnlEur: livePnl,
    pnlPct,
    ageSec,
    trailing,
    rr,
    pricePath,
  };
}

function formatTrainedDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const yy = String(d.getUTCFullYear()).slice(-2);
  return `${dd}/${mm}/${yy}`;
}
