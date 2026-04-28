import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  BadgeComponent,
  CardBodyComponent,
  CardComponent,
  CardHeaderComponent,
  ColComponent,
  ContainerComponent,
  RowComponent,
  TableDirective,
} from '@coreui/angular';
import { FormSelectDirective } from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { NotificationCenterService } from '../../core/services/notification-center.service';
import { AppNotification } from '../../core/models';

@Component({
  selector: 'app-notifications',
  templateUrl: './notifications.component.html',
  styleUrl: './notifications.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ContainerComponent, RowComponent, ColComponent,
    CardComponent, CardHeaderComponent, CardBodyComponent,
    TableDirective, BadgeComponent, IconDirective, FormSelectDirective,
  ],
})
export class NotificationsComponent implements OnInit {
  readonly #notifService = inject(NotificationCenterService);
  private readonly destroyRef = inject(DestroyRef);

  readonly notifications = signal<AppNotification[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = 20;
  readonly loading = signal(false);

  // Filters
  readonly filterAlertType = signal('');
  readonly filterSeverity = signal('');
  readonly filterEpic = signal('');
  readonly filterUnreadOnly = signal(false);

  readonly alertTypes = [
    'TRADE_OPENED', 'TRADE_CLOSED', 'SIGNAL_GENERATED',
    'CIRCUIT_BREAKER', 'DRAWDOWN_EXCEEDED', 'CONSECUTIVE_LOSSES',
    'RISK_LIMIT_BREACH', 'POSITION_STUCK', 'DATABASE_FAILURE',
    'BROKER_DISCONNECTED', 'BROKER_ERROR', 'SYSTEM_ERROR',
    'BACKUP_START', 'BACKUP_COMPLETE',
  ];

  readonly severities = ['CRITICAL', 'WARNING', 'INFO'];

  ngOnInit(): void {
    this.loadNotifications();
  }

  loadNotifications(): void {
    this.loading.set(true);
    const params: Record<string, any> = {
      page: this.page(),
      page_size: this.pageSize,
    };
    if (this.filterAlertType()) params['alert_type'] = this.filterAlertType();
    if (this.filterSeverity()) params['severity'] = this.filterSeverity();
    if (this.filterEpic()) params['epic'] = this.filterEpic();
    if (this.filterUnreadOnly()) params['is_read'] = false;

    this.#notifService.loadPage(params).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: res => {
        if (res.success) {
          this.notifications.set(res.data.notifications);
          this.total.set(res.data.total);
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  applyFilters(): void {
    this.page.set(1);
    this.loadNotifications();
  }

  resetFilters(): void {
    this.filterAlertType.set('');
    this.filterSeverity.set('');
    this.filterEpic.set('');
    this.filterUnreadOnly.set(false);
    this.page.set(1);
    this.loadNotifications();
  }

  markAsRead(id: number): void {
    this.#notifService.markAsRead(id);
    this.notifications.update(list =>
      list.map(n => n.id === id ? { ...n, is_read: true } : n)
    );
  }

  markAllRead(): void {
    this.#notifService.markAllRead();
    this.notifications.update(list =>
      list.map(n => ({ ...n, is_read: true }))
    );
  }

  deleteNotification(id: number): void {
    this.#notifService.deleteNotification(id);
    this.notifications.update(list => list.filter(n => n.id !== id));
    this.total.update(t => Math.max(0, t - 1));
  }

  goToPage(p: number): void {
    this.page.set(p);
    this.loadNotifications();
  }

  get totalPages(): number {
    return Math.ceil(this.total() / this.pageSize);
  }

  /** Stable list of page indices for the pagination row. Recomputed only
   *  when totalPages changes (signal dependency on this.total()). */
  readonly pageIndices = computed<readonly number[]>(() =>
    Array.from({ length: Math.ceil(this.total() / this.pageSize) }, (_, i) => i + 1),
  );

  severityColor(severity: string): string {
    switch (severity) {
      case 'CRITICAL': return 'danger';
      case 'WARNING': return 'warning';
      default: return 'info';
    }
  }

  timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'ora';
    if (mins < 60) return `${mins}m fa`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h fa`;
    const days = Math.floor(hours / 24);
    return `${days}g fa`;
  }
}
