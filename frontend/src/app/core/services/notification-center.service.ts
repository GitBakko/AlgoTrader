import { Injectable, inject, signal, computed } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AppNotification, NotificationListResponse } from '../models';
import { ApiService } from './api.service';

/**
 * H2-FE fix: removed `OnDestroy` — Angular never calls `ngOnDestroy` on
 * root-scoped services so the previous handler was unreachable. The WS
 * is now torn down explicitly via `disconnectWs()` called from
 * `AuthService.clearAuth()` so the reconnect-loop stops on logout.
 *
 * H4-FE-AUDIT: migrated from raw HttpClient to ApiService for envelope
 * consistency. M3-CORE: single-init guard prevents the duplicate REST
 * burst caused by both DefaultHeader + Dashboard injecting + calling
 * init() on first dashboard load.
 */
@Injectable({ providedIn: 'root' })
export class NotificationCenterService {
  private readonly api = inject(ApiService);
  private readonly wsUrl = `${environment.wsUrl}/ws/notifications`;
  private initialized = false;

  readonly notifications = signal<AppNotification[]>([]);
  readonly unreadCount = signal(0);

  /** Muted alert types version counter — triggers recomputation when localStorage changes */
  private readonly mutedVersion = signal(0);

  private getMutedTypes(): Set<string> {
    return new Set(JSON.parse(localStorage.getItem('mantis-muted-alerts') || '[]'));
  }

  /** Bump this after changing localStorage muted alerts from Settings */
  refreshMutedFilter(): void {
    this.mutedVersion.update(v => v + 1);
  }

  readonly filteredNotifications = computed(() => {
    this.mutedVersion(); // subscribe to version changes
    const muted = this.getMutedTypes();
    return this.notifications().filter(n => !muted.has(n.alert_type));
  });

  readonly filteredUnreadCount = computed(() =>
    this.filteredNotifications().filter(n => !n.is_read).length
  );

  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private readonly MAX_RECONNECT_DELAY = 60000;
  private readonly BASE_DELAY = 2000;
  /** H2-FE: when true, the onclose handler skips its reconnect timer
   *  so logout closes the WS cleanly. Reset on each `connectWs()`. */
  private intentionalDisconnect = false;

  /** Initialize: load from REST + connect WS. M3-CORE: idempotent. */
  init(): void {
    if (this.initialized) return;
    this.initialized = true;
    this.loadUnreadCount();
    this.loadRecent();
    this.connectWs();
  }

  /** Load recent notifications for dropdown */
  loadRecent(): void {
    this.api.get<NotificationListResponse>('/api/notifications/', { page: 1, page_size: 20 })
      .subscribe({
        next: data => {
          if (data?.notifications) this.notifications.set(data.notifications);
        }
      });
  }

  /** Load unread count for badge */
  loadUnreadCount(): void {
    this.api.get<{ count: number }>('/api/notifications/unread-count')
      .subscribe({
        next: data => {
          if (data) this.unreadCount.set(data.count);
        }
      });
  }

  /** Load paginated notifications (for full page) */
  loadPage(params: {
    page?: number;
    page_size?: number;
    alert_type?: string;
    severity?: string;
    epic?: string;
    is_read?: boolean;
  } = {}): Observable<NotificationListResponse> {
    return this.api.get<NotificationListResponse>('/api/notifications/', { ...params });
  }

  /** Mark single notification as read */
  markAsRead(id: number): void {
    this.api.put<unknown>(`/api/notifications/${id}/read`, {}).subscribe({
      next: () => {
        this.notifications.update(list =>
          list.map(n => n.id === id ? { ...n, is_read: true } : n)
        );
        this.unreadCount.update(c => Math.max(0, c - 1));
      }
    });
  }

  /** Mark all as read */
  markAllRead(): void {
    this.api.put<unknown>('/api/notifications/read-all', {}).subscribe({
      next: () => {
        this.notifications.update(list =>
          list.map(n => ({ ...n, is_read: true }))
        );
        this.unreadCount.set(0);
      }
    });
  }

  /** Delete a notification */
  deleteNotification(id: number): void {
    this.api.delete<unknown>(`/api/notifications/${id}`).subscribe({
      next: () => {
        const wasUnread = this.notifications().find(n => n.id === id && !n.is_read);
        this.notifications.update(list => list.filter(n => n.id !== id));
        if (wasUnread) {
          this.unreadCount.update(c => Math.max(0, c - 1));
        }
      }
    });
  }

  /** Connect to /ws/notifications for real-time push */
  private connectWs(): void {
    if (this.ws) return;
    this.intentionalDisconnect = false;
    this.ws = new WebSocket(this.wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const notif: AppNotification = JSON.parse(event.data);
        if (notif.alert_type) {
          // Prepend to list, cap at 50
          this.notifications.update(list => [notif, ...list].slice(0, 50));
          if (!notif.is_read) {
            this.unreadCount.update(c => c + 1);
          }
        }
      } catch {
        // Ignore non-JSON messages (pong, heartbeat)
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      if (this.intentionalDisconnect) return;
      const delay = Math.min(
        this.BASE_DELAY * Math.pow(2, this.reconnectAttempts),
        this.MAX_RECONNECT_DELAY
      );
      this.reconnectAttempts++;
      setTimeout(() => this.connectWs(), delay);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  /** H2-FE public teardown — call from AuthService.clearAuth(). */
  disconnectWs(): void {
    this.intentionalDisconnect = true;
    this.ws?.close();
    this.ws = null;
    this.reconnectAttempts = 0;
  }
}
