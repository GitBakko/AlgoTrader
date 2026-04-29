import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule, DatePipe, DecimalPipe } from '@angular/common';
import { EpicLogoComponent } from '../../../../shared/components/epic-logo/epic-logo.component';
import { SignalAuditService } from '../../../../core/services/signal-audit.service';
import { TradingService } from '../../../../core/services/trading.service';
import type { PositionEvent } from '../../../../core/models';
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
  imports: [CommonModule, DatePipe, DecimalPipe, EpicLogoComponent],
  templateUrl: './position-detail-drawer.component.html',
  styleUrls: ['./position-detail-drawer.component.scss'],
})
export class PositionDetailDrawerComponent {
  private readonly auditService = inject(SignalAuditService);
  private readonly trading = inject(TradingService);
  private readonly destroyRef = inject(DestroyRef);

  readonly position = input<PaperTradingPosition | null>(null);
  readonly currency = input<string>('USD');

  readonly closed = output<void>();

  readonly activeTab = signal<DrawerTab>('overview');

  /** Event timeline for the History tab. Refetched every time the History
   *  tab becomes visible for the current position (no `lastFetchedDealId`
   *  caching) — the endpoint is cheap and a stale empty state is more
   *  user-hostile than one extra GET. */
  readonly events = signal<PositionEvent[] | null>(null);
  readonly eventsLoading = signal<boolean>(false);
  readonly eventsError = signal<string | null>(null);
  /** Track which deal we are currently fetching for, so a stale in-flight
   *  response from a previous deal cannot overwrite the new deal's events. */
  private inflightDealId: string | null = null;

  constructor() {
    // Reset event state when the drawer's position changes (different deal).
    effect(() => {
      const id = this.position()?.id ?? null;
      if (id !== this.inflightDealId) {
        this.events.set(null);
        this.eventsError.set(null);
      }
    });

    // Fetch whenever the History tab is active for the current deal.
    // No caching — the response is small and freshness is more important
    // than skipping a HTTP round-trip.
    effect(() => {
      const tab = this.activeTab();
      const id = this.position()?.id;
      if (tab === 'history' && id) {
        this.fetchEvents(id);
      }
    });
  }

  retryFetchEvents(): void {
    const id = this.position()?.id;
    if (id) {
      this.fetchEvents(id);
    }
  }

  private fetchEvents(dealId: string): void {
    this.inflightDealId = dealId;
    this.eventsLoading.set(true);
    this.eventsError.set(null);
    this.trading
      .fetchPositionEvents(dealId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          // Drop responses for stale deal IDs (drawer switched mid-flight).
          if (this.inflightDealId !== dealId) return;
          this.events.set(data?.events ?? []);
          this.eventsLoading.set(false);
        },
        error: () => {
          if (this.inflightDealId !== dealId) return;
          this.eventsError.set('Caricamento eventi fallito');
          this.eventsLoading.set(false);
        },
      });
  }

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
