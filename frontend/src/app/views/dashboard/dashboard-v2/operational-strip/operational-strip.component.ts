import { Component, ChangeDetectionStrategy, computed, inject, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { WebSocketService } from '../../../../core/services/websocket.service';
import { MarketStatusService } from '../../../../core/services/market-status.service';

/**
 * DASHBOARD v2 — Deliverable B
 *
 * TODO — BACKEND (next sprint, see docs/plans/2026-04-23_dashboard-v2-sprint.md):
 *   - `ws.latencyMs` / `/ws/prices` ping/pong round-trip
 *   - `performance.daily_trade_count` (derivato oggi da equity_curve last row)
 *   - `AiModelService.currentModel()` / `GET /api/models/current`
 *   - Session label multi-venue (LONDON / NY / TOKYO) server-side
 *
 * Finché l'endpoint non esiste, i tile corrispondenti renderizzano skeleton
 * marker visibile (`--`) senza mai inventare numeri (§14 Definition of Done).
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

  /** Default epic used to sample market session state. */
  readonly sessionEpic = 'XAUUSD';

  readonly marketStatusSig = signal<{ is_open: boolean; status: string } | null>(null);

  /** Ticks every 30s so session label stays in sync with UTC hour. */
  readonly nowTick = signal<number>(Date.now());
  private readonly nowTimer = setInterval(() => this.nowTick.set(Date.now()), 30_000);

  /** Derive session label from UTC hour — decorative until backend provides canonical label. */
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

  /** trades today = last row of equity curve (backend computes per-day trade_count). */
  readonly tradesToday = computed<number | null>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return null;
    const today = new Date().toISOString().slice(0, 10);
    const todayRow = curve.find(p => (p.date ?? '').slice(0, 10) === today);
    if (todayRow) return todayRow.trade_count ?? 0;
    const last = curve[curve.length - 1];
    return last?.trade_count ?? 0;
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
    const secs = (st.iteration_count ?? 0) * (st.interval_seconds ?? 0);
    if (secs <= 0) return '—';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  });

  /** Execution mode (PAPER/DEMO/LIVE) bubbled from paperStatus. */
  readonly executionMode = computed<string>(() =>
    this.trading.paperStatus()?.execution_mode ?? '—'
  );

  constructor() {
    effect(async () => {
      // Re-resolve market status whenever the dashboard polls (cheap, cached 60s).
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
