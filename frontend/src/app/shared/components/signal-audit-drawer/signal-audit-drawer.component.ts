import { Component, ChangeDetectionStrategy, inject, HostListener, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SignalAuditService } from '../../../core/services/signal-audit.service';
import { TradingService } from '../../../core/services/trading.service';
import { EpicLogoComponent } from '../epic-logo/epic-logo.component';
import { BadgeComponent, SpinnerComponent } from '@coreui/angular';
import { SlCooldownInfo, PaperPosition } from '../../../core/models';
import { WebSocketService } from '../../../core/services/websocket.service';

@Component({
  selector: 'app-signal-audit-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, EpicLogoComponent, BadgeComponent, SpinnerComponent],
  templateUrl: './signal-audit-drawer.component.html',
  styleUrls: ['./signal-audit-drawer.component.scss'],
})
export class SignalAuditDrawerComponent {
  readonly auditService = inject(SignalAuditService);
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);

  // Live position for this epic (if open on broker)
  readonly livePosition = computed<PaperPosition | null>(() => {
    const epic = this.auditService.currentAudit()?.epic;
    if (!epic) return null;
    return this.trading.paperPositions().find(p => p.epic === epic) ?? null;
  });

  // Live P&L for open position
  readonly livePnl = computed<number | null>(() => {
    const pos = this.livePosition();
    if (!pos) return null;
    const tick = this.ws.prices()[pos.epic];
    if (!tick) return null;
    const current = pos.direction === 'BUY' ? tick.bid : tick.offer;
    const diff = pos.direction === 'BUY'
      ? current - pos.level
      : pos.level - current;
    return Math.round(diff * pos.size * 100) / 100;
  });

  // Get SL cooldown for the current audit's epic from the latest signal data
  readonly epicCooldown = computed<SlCooldownInfo | null>(() => {
    const epic = this.auditService.currentAudit()?.epic;
    if (!epic) return null;
    // Find the most recent signal for this epic that has cooldown info
    const signals = this.trading.paperSignals();
    for (const sig of signals) {
      if (sig.epic === epic && sig.sl_cooldown) return sig.sl_cooldown;
    }
    return null;
  });

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.auditService.isOpen()) {
      this.auditService.close();
    }
  }

  onBackdropClick(): void {
    this.auditService.close();
  }

  voteEntries(): [string, any][] {
    const votes = this.auditService.currentAudit()?.features?.votes;
    if (!votes) return [];
    return Object.entries(votes);
  }

  gateEntries(): [string, any][] {
    const gates = this.auditService.currentAudit()?.features?.gates;
    if (!gates) return [];
    return Object.entries(gates);
  }

  gatesPassed(): number {
    return this.gateEntries().filter(([, g]) => g?.passed === true).length;
  }

  gatesTotal(): number {
    return this.gateEntries().filter(([, g]) => g !== null).length;
  }

  voteLabel(key: string): string {
    const labels: Record<string, string> = {
      // ScalpScore votes
      ema: 'EMA', rsi: 'RSI', macd: 'MACD',
      volume: 'Volume', adx: 'ADX', bb_keltner: 'BB/Keltner',
      sentiment: 'Sentiment',
      // MeanReversion votes
      z_score: 'Z-Score', vwap_z: 'VWAP Z', bb_pctb: 'BB %B',
    };
    return labels[key] ?? key.toUpperCase();
  }

  gateLabel(key: string): string {
    const labels: Record<string, string> = {
      // ScalpScore gates
      session: 'Sessione', dead_market: 'Mercato Morto',
      vwap: 'VWAP', htf: 'HTF Trend', confluence: 'Confluenza',
      data_quality: 'Data Quality',
      // MeanReversion gates
      trending_filter: 'Filtro Trend',
      z_threshold: 'Soglia Z',
      quality_gate: 'Quality Gate',
      ml_agreement: 'ML Agreement',
    };
    return labels[key] ?? key;
  }

  mlAgreementColor(): string {
    const ml = this.auditService.currentAudit()?.features?.ml;
    if (!ml) return 'secondary';
    switch (ml.agreement) {
      case 'agree': return 'success';
      case 'neutral': return 'warning';
      case 'disagree': return 'danger';
      default: return 'secondary';
    }
  }

  mlAgreementLabel(): string {
    const ml = this.auditService.currentAudit()?.features?.ml;
    if (!ml) return '';
    switch (ml.agreement) {
      case 'agree': return 'Concorda';
      case 'neutral': return 'Neutrale';
      case 'disagree': return 'Disaccordo';
      default: return ml.agreement;
    }
  }

  snapshotEntries(): [string, any][] {
    const snapshot = this.auditService.currentAudit()?.features?.market_snapshot;
    if (!snapshot) return [];
    return Object.entries(snapshot);
  }

  snapshotLabel(key: string): string {
    const labels: Record<string, string> = {
      price: 'Prezzo', atr: 'ATR', rsi: 'RSI', adx: 'ADX',
      vwap: 'VWAP', htf_bias: 'HTF Bias', volume: 'Volume',
      bb_width: 'BB Width',
      vwap_z: 'VWAP Z',
      bb_pctb: 'BB %B',
      sentiment_composite: 'Sentiment',
    };
    return labels[key] ?? key;
  }

  formatValue(val: any): string {
    if (val === null || val === undefined) return '-';
    if (typeof val === 'number') return val.toFixed(4);
    return String(val);
  }

  /** Confidence tone tier — mirrors heatmap/feed thresholds so the same
   *  signal color shows up consistently across the cockpit. */
  confidenceTone(conf: number | null | undefined): 'high' | 'mid' | 'low' | 'none' {
    if (conf === null || conf === undefined) return 'none';
    const pct = conf * 100;
    if (pct >= 50) return 'high';
    if (pct >= 30) return 'mid';
    if (pct > 0) return 'low';
    return 'none';
  }

  /** Map a vote weight (-1, 0, +1) to a fill percentage of the bar half.
   *  Each side of the bar represents 100%, so a +1 vote = 100% right fill,
   *  a 0 vote = 0%. Built so the layout extends naturally to ±2 votes if
   *  an indicator group ever returns stronger weights. */
  voteFillPct(value: number | null | undefined): number {
    if (value === null || value === undefined) return 0;
    return Math.min(100, Math.abs(value) * 100);
  }

  /** "BUY 4 · SELL 2" header used in the votes card for a quick scan. */
  voteSummary(): string {
    const entries = this.voteEntries();
    if (entries.length === 0) return '';
    let buy = 0;
    let sell = 0;
    for (const [, v] of entries) {
      const value = v?.value ?? 0;
      if (value > 0) buy += value;
      else if (value < 0) sell += Math.abs(value);
    }
    return `· BUY ${buy} / SELL ${sell}`;
  }

  /** Compact one-liner summary to display on the right of a gate row. */
  gateDetail(key: string, gate: any): string {
    if (!gate) return '';
    if (gate.reason) return String(gate.reason);
    switch (key) {
      // ScalpScore gates
      case 'session':
        return `mult ${(gate.session_mult ?? 0).toFixed(1)} · ${gate.zone ?? ''}`.trim();
      case 'dead_market':
        return `ADX ${gate.adx?.toFixed?.(1) ?? gate.adx ?? '—'}`;
      case 'vwap':
        return gate.bias ? `bias ${gate.bias}` : '';
      case 'htf':
        return gate.htf_bias ? `bias ${gate.htf_bias}` : '';
      case 'confluence':
        return `${gate.buy_count ?? 0}/${gate.effective_min ?? 0} BUY · ${gate.sell_count ?? 0} SELL`;
      case 'data_quality':
        return gate.passed === false ? 'missing data' : 'OK';
      // MeanReversion gates
      case 'trending_filter':
        return `ADX ${gate.adx?.toFixed?.(1) ?? '—'} / max ${gate.adx_max ?? '—'}`;
      case 'z_threshold': {
        const z = gate.z;
        const entry = gate.z_entry;
        return `|z| ${(Math.abs(Number(z) || 0)).toFixed(2)} / ${entry}`;
      }
      case 'quality_gate':
        return `min ${gate.min_quality ?? '—'}`;
      case 'ml_agreement':
        return `ML ${gate.ml_direction ?? '—'} · MR ${gate.mr_direction ?? '—'}`;
      default:
        return '';
    }
  }

  /** Pipeline-stage state used in the header chain (passed/failed/neutral).
   *  Drives the dot color so the user sees at a glance which stage tripped
   *  the rejection. */
  stageState(stage: 'strategy' | 'ml' | 'risk' | 'outcome'): 'passed' | 'failed' | 'neutral' {
    const audit = this.auditService.currentAudit();
    if (!audit) return 'neutral';
    const features = audit.features || {};
    if (stage === 'outcome') {
      return audit.status === 'EXECUTED' ? 'passed' : audit.status === 'REJECTED' ? 'failed' : 'neutral';
    }
    if (stage === 'strategy') {
      const gates = features.gates;
      if (!gates) return 'neutral';
      const allPass = Object.values(gates).every(
        (g: any) => g === null || g === undefined || g.passed !== false,
      );
      return allPass ? 'passed' : 'failed';
    }
    if (stage === 'ml') {
      const ml = features.ml;
      if (!ml) return 'neutral';
      if (ml.agreement === 'agree') return 'passed';
      if (ml.agreement === 'disagree') return 'failed';
      return 'neutral';
    }
    if (stage === 'risk') {
      const risk = features.risk;
      if (!risk) return 'neutral';
      const cb = risk.circuit_breakers?.passed;
      const dd = risk.drawdown?.passed;
      if (cb === false || dd === false) return 'failed';
      if (cb === true && dd === true) return 'passed';
      return 'neutral';
    }
    return 'neutral';
  }
}
