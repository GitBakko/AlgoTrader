import { Component, ChangeDetectionStrategy, inject, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  BadgeComponent,
  DropdownComponent,
  DropdownItemDirective,
  DropdownMenuDirective,
  DropdownToggleDirective,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { NotificationCenterService } from '../../../../core/services/notification-center.service';

@Component({
  selector: 'app-notification-dropdown',
  templateUrl: './notification-dropdown.component.html',
  styleUrl: './notification-dropdown.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    BadgeComponent,
    DropdownComponent,
    DropdownToggleDirective,
    DropdownMenuDirective,
    DropdownItemDirective,
    IconDirective,
    RouterLink,
  ],
})
export class NotificationDropdownComponent {
  readonly #notifService = inject(NotificationCenterService);
  readonly unreadCount = this.#notifService.filteredUnreadCount;
  readonly notifications = computed(() => this.#notifService.filteredNotifications().slice(0, 10));

  markAsRead(id: number): void {
    this.#notifService.markAsRead(id);
  }

  markAllRead(): void {
    this.#notifService.markAllRead();
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
