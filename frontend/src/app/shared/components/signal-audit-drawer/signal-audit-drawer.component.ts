import { Component, ChangeDetectionStrategy, inject, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SignalAuditService } from '../../../core/services/signal-audit.service';
import { EpicLogoComponent } from '../epic-logo/epic-logo.component';
import { BadgeComponent, SpinnerComponent } from '@coreui/angular';

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
      ema: 'EMA', rsi: 'RSI', macd: 'MACD',
      volume: 'Volume', adx: 'ADX', bb_keltner: 'BB/Keltner',
    };
    return labels[key] ?? key.toUpperCase();
  }

  gateLabel(key: string): string {
    const labels: Record<string, string> = {
      session: 'Sessione', dead_market: 'Mercato Morto',
      vwap: 'VWAP', htf: 'HTF Trend', confluence: 'Confluenza',
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
    };
    return labels[key] ?? key;
  }

  formatValue(val: any): string {
    if (val === null || val === undefined) return '-';
    if (typeof val === 'number') return val.toFixed(4);
    return String(val);
  }
}
