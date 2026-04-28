import { Component, ChangeDetectionStrategy, computed, inject, output, signal, effect, input, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { WebSocketService } from '../../../../core/services/websocket.service';
import { MarketStatusService } from '../../../../core/services/market-status.service';
import { currencySymbol, formatMoneyIt, formatMoneyCompactIt } from '../shared/currency.util';

/**
 * DASHBOARD v2 — OperationalStrip (3-zone rewrite, Phase 2).
 *
 * Zone layout:
 *   grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) auto;
 *
 * ZONE 1 — Live P&L hero
 *   session label + dot pulse + `LIVE · <SESSION>` · hero €daily_pnl · delta%
 *   footer line: equity · trades today · peak intraday
 *
 * ZONE 2 — Open Positions N/maxSlots
 *   header right: Kelly ½ · K slots free · KILL SWITCH button
 *   grid of mini-cards for each paper position (up to 4 visible)
 *
 * ZONE 3 — System 2x3
 *   [Breakers N/6 OK] [WS Live]     [Broker Capital]
 *   [Mode DEMO]      [Swap -0.04%] [Regime Trend↑]
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
  readonly maxSlots = 8;
  readonly circuitBreakersTotal = 6;
  readonly killBusy = input<boolean>(false);
  readonly killClicked = output<void>();
  /** Emitted when a paper-position card is clicked — parent uses it
   *  to drive the overnight-swap tile's epic binding. */
  readonly positionSelected = output<string>();
  /** Epic currently highlighted as the swap-card source (optional,
   *  parent-controlled). */
  readonly selectedEpic = input<string | null>(null);

  readonly marketStatusSig = signal<{ is_open: boolean; status: string } | null>(null);

  readonly nowTick = signal<number>(Date.now());

  readonly ws$ = this.ws;

  // ── ZONE 1: Live P&L hero ─────────────────────────────────────
  readonly overview = this.trading.overview;
  /** Hero P&L = today_realized + sum(open.upl) — true "live" daily P&L. */
  readonly dailyPnl = computed<number>(() => {
    const ov = this.overview();
    if (!ov) return 0;
    return ov.live_daily_pnl ?? ov.daily_pnl ?? 0;
  });
  readonly equity   = computed<number | null>(() => this.overview()?.equity ?? null);
  readonly currency = computed<string>(() => this.overview()?.currency ?? 'USD');

  /** Realized P&L today (broker-side closed-trade sum). */
  readonly realizedToday = computed<number>(() => this.overview()?.today_realized_pnl ?? 0);

  /** Sum of open-position UPL — true live unrealized (recomputed each WS tick). */
  readonly unrealizedLive = computed<number>(() =>
    this.positions().reduce((s, p) => s + (p.upl ?? 0), 0),
  );

  /**
   * Live equity = broker-side equity + sum(upl).
   * Backend `overview.equity` is polled (10s / 60s); adding client-computed
   * UPL keeps the headline in sync with WS price ticks without extra calls.
   */
  readonly equityLive = computed<number | null>(() => {
    const eq = this.overview()?.equity;
    if (eq == null) return null;
    return eq + this.unrealizedLive();
  });

  readonly dailyPct = computed<number | null>(() => {
    const ov = this.overview();
    if (!ov || !ov.equity) return null;
    const pnl = ov.live_daily_pnl ?? ov.daily_pnl ?? 0;
    return (pnl / ov.equity) * 100;
  });

  readonly sessionLabel = computed<string>(() => {
    this.nowTick();
    const h = new Date().getUTCHours();
    const parts: string[] = [];
    if (h >= 0 && h < 8) parts.push('TOKYO');
    if (h >= 7 && h < 16) parts.push('LONDON');
    if (h >= 12 && h < 21) parts.push('NY');
    if (parts.length === 0) parts.push('AFTER-HRS');
    return parts.join(' · ');
  });

  readonly sessionOpen = computed<boolean>(() => this.marketStatusSig()?.is_open ?? false);

  /** Trades closed in the active timeframe window. */
  readonly tradesToday = computed<number>(() => this.trading.performance()?.trade_count ?? 0);

  /** Peak daily P&L across the active timeframe window (from equityCurve). */
  readonly peakIntraday = computed<number>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) {
      const daily = this.dailyPnl();
      return Math.max(daily, 0);
    }
    let peak = -Infinity;
    for (const p of curve) {
      const v = p.daily_pnl ?? 0;
      if (v > peak) peak = v;
    }
    return peak === -Infinity ? 0 : peak;
  });

  // ── ZONE 2: Open Positions ────────────────────────────────────
  readonly positions = this.trading.paperPositions;
  readonly openCount = computed<number>(() => this.positions().length);

  readonly visiblePositions = computed(() => this.positions().slice(0, 4));

  readonly kellyLabel = computed<string>(() => {
    const ks = this.trading.paperStatus()?.kelly_stats;
    if (!ks) return '—';
    const frac = ks.half_kelly ?? ks.kelly_fraction ?? 0;
    return `½ · ${(frac * 100).toFixed(0)}%`;
  });

  readonly slotsFree = computed<number>(() => Math.max(0, this.maxSlots - this.openCount()));

  /** Live mark price for an epic, from ws prices signal. */
  markPrice(epic: string): number | null {
    const prices = this.ws.prices();
    const row = prices[epic];
    if (!row) return null;
    return (row.bid + row.offer) / 2;
  }

  positionPct(pos: { upl?: number | null; level?: number; size?: number }): number | null {
    const upl = pos.upl ?? null;
    if (upl == null || !pos.level || !pos.size) return null;
    const notional = pos.level * pos.size;
    if (!notional) return null;
    return (upl / notional) * 100;
  }

  /** Broker uses BUY/SELL; some legacy code uses LONG/SHORT. Normalize. */
  isLong(direction: string): boolean {
    const d = (direction || '').toUpperCase();
    return d === 'BUY' || d === 'LONG';
  }

  /** P&L format with broker currency, 2 decimals. "+$1.270,54" / "−€57,23". */
  formatPnlCompact(n: number): string {
    return formatMoneyIt(n, this.currency());
  }

  // ── ZONE 3: System 2x3 ───────────────────────────────────────
  readonly circuitBreakersTripped = computed<number>(() => {
    const raw = this.trading.paperStatus()?.circuit_breakers_tripped;
    if (!raw) return 0;
    if (Array.isArray(raw)) return raw.length;
    return Object.keys(raw).length;
  });

  readonly breakersLabel = computed(() => {
    const tripped = this.circuitBreakersTripped();
    return `${this.circuitBreakersTotal - tripped}/${this.circuitBreakersTotal} OK`;
  });

  readonly executionMode = computed<string>(() =>
    this.trading.paperStatus()?.execution_mode ?? '—',
  );

  /** Compact swap display for the session epic. */
  readonly swapLabel = computed<string>(() => {
    const s = this.trading.overnightSwap()[this.sessionEpic];
    if (!s) return '—';
    return `${s.long_rate_pct > 0 ? '+' : ''}${s.long_rate_pct.toFixed(3)}%`;
  });

  /** Regime label — uses Allocation.regime when loaded. */
  readonly regimeLabel = computed<string>(() => {
    const alloc = this.trading.allocationData();
    if (alloc?.regime) return this.prettyRegime(alloc.regime);
    return '—';
  });

  private prettyRegime(r: string): string {
    const up = r.toUpperCase();
    if (up.includes('TREND') && up.includes('UP')) return 'Trend↑';
    if (up.includes('TREND') && up.includes('DOWN')) return 'Trend↓';
    if (up.includes('RANGE') || up.includes('CHOP')) return 'Range';
    if (up.includes('VOL')) return 'Vol-spike';
    return r.slice(0, 10);
  }

  constructor() {
    const destroyRef = inject(DestroyRef);
    const timer = setInterval(() => this.nowTick.set(Date.now()), 30_000);
    destroyRef.onDestroy(() => clearInterval(timer));

    effect(() => {
      this.nowTick();
      void this.refreshMarketStatus();
    });
  }

  private async refreshMarketStatus(): Promise<void> {
    try {
      const status = await this.marketStatus.getMarketStatus(this.sessionEpic);
      this.marketStatusSig.set({ is_open: status.is_open, status: status.status });
    } catch {
      // silent — market status cache falls back internally
    }
  }

  onKill(): void {
    this.killClicked.emit();
  }

  // ── Formatters (use shared currency.util) ───────────────────
  formatMoney(n: number): string {
    return formatMoneyIt(n, this.currency());
  }

  formatMoneyCompact(n: number): string {
    return formatMoneyCompactIt(n, this.currency());
  }

  formatEquity(n: number): string {
    return formatMoneyIt(n, this.currency(), { signed: false });
  }
}
