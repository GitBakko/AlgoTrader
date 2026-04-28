import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { EpicLogoComponent } from '../../../../shared/components/epic-logo/epic-logo.component';
import { SignalAuditService } from '../../../../core/services/signal-audit.service';
import type { PaperTradingPosition } from '../../../../core/models/paper-trading';

type DrawerTab = 'overview' | 'audit' | 'history';

/**
 * MDL-02 — right-side slide-in drawer (380px) with three tabs.
 * Triggered from `position-card.detailsClicked` to give a deeper view of an
 * open position without leaving the cockpit.
 */
@Component({
  selector: 'app-position-detail-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DecimalPipe, EpicLogoComponent],
  templateUrl: './position-detail-drawer.component.html',
  styleUrls: ['./position-detail-drawer.component.scss'],
})
export class PositionDetailDrawerComponent {
  private readonly auditService = inject(SignalAuditService);

  readonly position = input<PaperTradingPosition | null>(null);
  readonly currency = input<string>('USD');

  readonly closed = output<void>();

  readonly activeTab = signal<DrawerTab>('overview');

  /** Static tab list — frozen so the template `@for` keeps a stable
   *  array reference across renders. */
  readonly tabs: readonly DrawerTab[] = ['overview', 'audit', 'history'];

  readonly isOpen = computed(() => this.position() !== null);

  readonly currencySym = computed(() => {
    const code = (this.currency() ?? 'USD').replace(/d$/, '');
    switch (code) {
      case 'USD': return '$';
      case 'EUR': return '€';
      case 'GBP': return '£';
      default:    return code + ' ';
    }
  });

  readonly inProfit = computed(() => (this.position()?.pnlEur ?? 0) >= 0);

  readonly distToSlPct = computed(() => {
    const p = this.position();
    if (!p?.current) return 0;
    return Math.abs(((p.stopLoss - p.current) / p.current) * 100);
  });

  readonly distToTpPct = computed(() => {
    const p = this.position();
    if (!p?.current) return 0;
    return Math.abs(((p.takeProfit - p.current) / p.current) * 100);
  });

  readonly ageLabel = computed(() => {
    const sec = this.position()?.ageSec ?? 0;
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    const remM = m % 60;
    if (h < 24) return remM > 0 ? `${h}h ${remM}m` : `${h}h`;
    const d = Math.floor(h / 24);
    return `${d}d ${h % 24}h`;
  });

  setTab(tab: DrawerTab): void {
    this.activeTab.set(tab);
  }

  /** Opens the global signal-audit drawer wired by `SignalAuditService`,
   *  re-using its rich body instead of duplicating it inside this drawer. */
  openFullAudit(): void {
    const p = this.position();
    if (!p) return;
    this.auditService.openByDealId(p.id, p.ticker);
    this.close();
  }

  close(): void {
    this.closed.emit();
  }

  onBackdropClick(): void {
    this.close();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.isOpen()) this.close();
  }
}
