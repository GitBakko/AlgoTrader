import { ChangeDetectionStrategy, Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { CockpitHeaderComponent, type CockpitMode, type CockpitState } from '../../shared/components/cockpit-header/cockpit-header.component';
import { TradingService } from '../../core/services/trading.service';
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
import { WebSocketService } from '../../core/services/websocket.service';
import type { PaperPosition } from '../../core/models';
import { epicColor } from '../../shared/constants/epic-colors';

const CIRCUIT_BREAKER_TOTAL = 6;
const DEFAULT_DD_GATE_PCT = 20;

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

  readonly stopBusy = signal(false);
  readonly emergencyBusy = signal(false);

  /** Wall-clock signal updated every 1s so `lastTickAgo` and dependent
   *  computeds (cockpit-header tick chip, ECG label) re-render every second
   *  even when the 10s polling cycle has not refreshed `paperStatus` yet. */
  readonly tickClock = signal(Date.now());

  readonly status = this.trading.paperStatus;
  readonly overview = this.trading.overview;
  readonly currency = computed<string>(() => this.overview()?.currency ?? 'USD');

  readonly state = computed<CockpitState>(() => {
    const s = this.status();
    if (!s) return 'IDLE';
    if ((s.error_count ?? 0) > 0) return 'ERROR';
    return s.running ? 'RUNNING' : 'IDLE';
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
      lastTickAgo: this.lastTickAgo() ?? 0,
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
    const now = this.tickClock();
    return broker.map((p) => adaptPosition(p, prices[p.epic], now));
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

  /** Build/footer label — extended in PR 5. */
  readonly buildTag = signal<string>('mantis · v2 shell');

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private clockTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.trading.loadPaperStatus();
    this.trading.loadRiskStatus();
    this.trading.loadOverview();
    this.trading.loadPaperPositions();
    this.ws.connectPrices();
    this.pollTimer = setInterval(() => {
      this.trading.loadPaperStatus();
      this.trading.loadRiskStatus();
      this.trading.loadOverview();
      this.trading.loadPaperPositions();
    }, 10_000);
    this.clockTimer = setInterval(() => this.tickClock.set(Date.now()), 1_000);
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
    // PR5 wires the audit drawer; for PR3 details are a no-op so the card
    // remains keyboard-focusable without breaking accessibility.
    void p;
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
    // PR3 leaves the spark as a 2-point line (entry → current). PR4 will
    // hydrate from the WS history buffer.
    pricePath: [p.level, current],
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
