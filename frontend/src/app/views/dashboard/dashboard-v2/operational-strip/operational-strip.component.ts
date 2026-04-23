import { Component, ChangeDetectionStrategy, computed, inject, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { WebSocketService } from '../../../../core/services/websocket.service';
import { MarketStatusService } from '../../../../core/services/market-status.service';

/**
 * DASHBOARD v2 — Deliverable B (fully wired)
 *
 * All tiles now read from live backend endpoints:
 *   - tile 1 Session      ← MarketStatusService + UTC-hour heuristic (D3:B)
 *   - tile 2 Broker WS    ← WebSocketService.latencyMs (ping/pong, §2.3)
 *   - tile 3 Trades today ← TradingService.performance().daily_trade_count (§2.5)
 *   - tile 4 Circuit br.  ← paperStatus.circuit_breakers_tripped
 *   - tile 5 Paper bot    ← paperStatus.uptime_seconds / started_at (§2.4)
 *   - tile 6 Model        ← TradingService.currentModels().primary (§2.4)
 */
@Component({
  selector: 'app-operational-strip',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './operational-strip.component.html',
  styleUrl: './operational-strip.component.scss',
})
export class OperationalStripComponent {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  private readonly marketStatus = inject(MarketStatusService);

  readonly sessionEpic = 'XAUUSD';

  readonly marketStatusSig = signal<{ is_open: boolean; status: string } | null>(null);

  readonly nowTick = signal<number>(Date.now());
  private readonly nowTimer = setInterval(() => this.nowTick.set(Date.now()), 30_000);

  readonly sessionLabel = computed<string>(() => {
    this.nowTick();
    const h = new Date().getUTCHours();
    const sessions: string[] = [];
    if (h >= 0 && h < 8) sessions.push('TOKYO');
    if (h >= 7 && h < 16) sessions.push('LONDON');
    if (h >= 12 && h < 21) sessions.push('NY');
    if (sessions.length === 0) sessions.push('AFTER-HRS');
    return sessions.join(' · ');
  });

  readonly sessionOpen = computed<boolean>(() => {
    const s = this.marketStatusSig();
    return s ? s.is_open : false;
  });

  readonly ws$ = this.ws;

  /** trades today = backend-computed count of positions opened in current UTC day. */
  readonly tradesToday = computed<number | null>(() => {
    const perf = this.trading.performance();
    if (perf?.daily_trade_count != null) return perf.daily_trade_count;
    // Fallback: derive from equity curve last row if backend field missing.
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return null;
    const today = new Date().toISOString().slice(0, 10);
    const todayRow = curve.find(p => (p.date ?? '').slice(0, 10) === today);
    if (todayRow) return todayRow.trade_count ?? 0;
    return curve[curve.length - 1]?.trade_count ?? 0;
  });

  readonly primaryModel = computed(() => this.trading.currentModels()?.primary ?? null);

  readonly primaryModelLabel = computed(() => {
    const m = this.primaryModel();
    if (!m) return '—';
    const type = (m.model_type || '').toUpperCase();
    return `${type}·${m.epic} v${m.version}`;
  });

  readonly primaryModelTrainedAt = computed(() => {
    const m = this.primaryModel();
    if (!m?.last_trained) return 'needs /api/models/current';
    try {
      const d = new Date(m.last_trained);
      const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
      if (days === 0) return 'trained today';
      if (days === 1) return 'trained 1d ago';
      return `trained ${days}d ago`;
    } catch {
      return m.last_trained;
    }
  });

  readonly circuitBreakersTrippedCount = computed<number>(() => {
    const raw = this.trading.paperStatus()?.circuit_breakers_tripped;
    if (!raw) return 0;
    if (Array.isArray(raw)) return raw.length;
    return Object.keys(raw).length;
  });

  readonly circuitBreakersTotal = 6;

  readonly paperBotRunning = computed<boolean>(() => !!this.trading.paperStatus()?.running);

  readonly paperBotUptimeText = computed<string>(() => {
    const st = this.trading.paperStatus();
    if (!st?.running) return '—';
    // Prefer backend wall-clock uptime; fall back to iteration × interval.
    const secs = st.uptime_seconds ?? (st.iteration_count ?? 0) * (st.interval_seconds ?? 0);
    if (secs <= 0) return '—';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  });

  readonly executionMode = computed<string>(() =>
    this.trading.paperStatus()?.execution_mode ?? '—'
  );

  constructor() {
    effect(async () => {
      this.nowTick();
      try {
        const status = await this.marketStatus.getMarketStatus(this.sessionEpic);
        this.marketStatusSig.set({ is_open: status.is_open, status: status.status });
      } catch {
        // silent — market status cache falls back internally
      }
    });
  }
}
