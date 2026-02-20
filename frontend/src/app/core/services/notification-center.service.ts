import { Injectable, inject, signal, computed, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { ApiResponse, AppNotification, NotificationListResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class NotificationCenterService implements OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/api/notifications`;
  private readonly wsUrl = `${environment.wsUrl}/ws/notifications`;

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

  /** Initialize: load from REST + connect WS */
  init(): void {
    this.loadUnreadCount();
    this.loadRecent();
    this.connectWs();
  }

  /** Load recent notifications for dropdown */
  loadRecent(): void {
    this.http.get<ApiResponse<NotificationListResponse>>(
      `${this.apiUrl}/?page=1&page_size=20`
    ).subscribe({
      next: res => {
        if (res.success) {
          this.notifications.set(res.data.notifications);
        }
      }
    });
  }

  /** Load unread count for badge */
  loadUnreadCount(): void {
    this.http.get<ApiResponse<{ count: number }>>(
      `${this.apiUrl}/unread-count`
    ).subscribe({
      next: res => {
        if (res.success) {
          this.unreadCount.set(res.data.count);
        }
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
  } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.page_size) query.set('page_size', String(params.page_size));
    if (params.alert_type) query.set('alert_type', params.alert_type);
    if (params.severity) query.set('severity', params.severity);
    if (params.epic) query.set('epic', params.epic);
    if (params.is_read !== undefined) query.set('is_read', String(params.is_read));

    return this.http.get<ApiResponse<NotificationListResponse>>(
      `${this.apiUrl}/?${query.toString()}`
    );
  }

  /** Mark single notification as read */
  markAsRead(id: number): void {
    this.http.put<ApiResponse<any>>(`${this.apiUrl}/${id}/read`, {}).subscribe({
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
    this.http.put<ApiResponse<any>>(`${this.apiUrl}/read-all`, {}).subscribe({
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
    this.http.delete<ApiResponse<any>>(`${this.apiUrl}/${id}`).subscribe({
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

  ngOnDestroy(): void {
    this.ws?.close();
    this.ws = null;
  }
}
