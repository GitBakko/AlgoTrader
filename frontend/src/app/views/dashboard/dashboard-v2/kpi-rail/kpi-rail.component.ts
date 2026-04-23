import { Component, ChangeDetectionStrategy, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TradingService } from '../../../../core/services/trading.service';
import { WebSocketService } from '../../../../core/services/websocket.service';

interface RailRow {
  label: string;
  value: string;
  sub: string;
  accent: 'profit' | 'loss' | 'warning' | 'cyan' | 'neutral' | 'todo';
  routerLink?: string;
  todo?: boolean;
}

/**
 * Right-pane KPI rail for DashboardV2 cockpit spine.
 *
 * TODO — BACKEND (next sprint): `performance.tp_hit_rate` field still
 * missing — last row renders skeleton placeholder.
 */
@Component({
  selector: 'app-kpi-rail',
  standalone: true,
  imports: [CommonModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './kpi-rail.component.html',
  styleUrl: './kpi-rail.component.scss',
})
export class KpiRailComponent {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);

  readonly overview = this.trading.overview;
  readonly riskStatus = this.trading.riskStatus;
  readonly performance = this.trading.performance;

  readonly allLivePositions = computed(() => {
    const positions = this.trading.paperPositions();
    const prices = this.ws.prices();
    return positions.map(pos => {
      if (pos.upl != null) return { ...pos, live_pnl: pos.upl };
      const tick = prices[pos.epic];
      if (!tick) return { ...pos, live_pnl: 0 };
      const currentPrice = pos.direction === 'BUY' ? tick.bid : tick.offer;
      const diff = pos.direction === 'BUY'
        ? currentPrice - pos.level
        : pos.level - currentPrice;
      return { ...pos, live_pnl: Math.round(diff * pos.size * 100) / 100 };
    });
  });

  readonly openPositionCount = computed(() => this.allLivePositions().length);

  readonly totalUnrealizedPnl = computed(() =>
    this.allLivePositions().reduce((sum, p) => sum + p.live_pnl, 0)
  );

  readonly netExposure = computed(() =>
    this.allLivePositions().reduce((sum, p) => sum + p.size * p.level, 0)
  );

  readonly drawdownPct = computed(() => {
    const rs = this.riskStatus();
    return rs ? rs.current_drawdown_pct * 100 : 0;
  });

  readonly rows = computed<RailRow[]>(() => {
    const ov = this.overview();
    const perf = this.performance();

    const dailyPnl = ov?.daily_pnl ?? 0;
    const drawdown = this.drawdownPct();
    const unrealized = this.totalUnrealizedPnl();

    return [
      {
        label: 'Daily P&L',
        value: this.fmtMoney(dailyPnl),
        sub: 'realized + unrealized',
        accent: dailyPnl >= 0 ? 'profit' : 'loss',
        routerLink: '/performance',
      },
      {
        label: 'Open positions',
        value: String(this.openPositionCount()),
        sub: 'paper trades live',
        accent: 'cyan',
        routerLink: '/positions',
      },
      {
        label: 'Unrealized P&L',
        value: this.fmtMoney(unrealized),
        sub: 'broker UPL',
        accent: unrealized >= 0 ? 'profit' : 'loss',
        routerLink: '/positions',
      },
      {
        label: 'Net exposure',
        value: '€' + this.netExposure().toLocaleString('it-IT', { minimumFractionDigits: 0, maximumFractionDigits: 0 }),
        sub: 'Σ size · level',
        accent: 'neutral',
      },
      {
        label: 'Drawdown',
        value: drawdown.toFixed(2) + '%',
        sub: 'from peak equity',
        accent: drawdown > 5 ? 'loss' : drawdown > 2 ? 'warning' : 'neutral',
      },
      {
        label: 'Sharpe (30d)',
        value: perf?.sharpe_ratio != null ? perf.sharpe_ratio.toFixed(2) : '—',
        sub: perf?.sortino_ratio != null ? 'Sortino ' + perf.sortino_ratio.toFixed(2) : 'needs 30d data',
        accent: 'cyan',
      },
      {
        label: 'Win rate',
        value: perf?.win_rate != null ? (perf.win_rate * 100).toFixed(1) + '%' : '—',
        sub: perf ? `${perf.win_count}W · ${perf.loss_count}L` : '—',
        accent: 'profit',
      },
      {
        label: 'Hit rate TP',
        value: '—',
        sub: 'needs perf.tp_hit_rate',
        accent: 'todo',
        todo: true,
      },
    ];
  });

  private fmtMoney(n: number): string {
    const sign = n > 0 ? '+' : n < 0 ? '−' : '';
    return `${sign}€${Math.abs(n).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}
