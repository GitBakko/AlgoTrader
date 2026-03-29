import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, inject, input, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DecimalPipe } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';

import {
  ColorModeService,
  ContainerComponent,
  DropdownComponent,
  DropdownItemDirective,
  DropdownMenuDirective,
  DropdownToggleDirective,
  HeaderComponent,
  HeaderNavComponent,
  HeaderTogglerDirective,
  NavItemComponent,
  NavLinkDirective,
  SidebarToggleDirective,
  TooltipDirective
} from '@coreui/angular';

import { IconDirective } from '@coreui/icons-angular';
import { WebSocketService } from '../../../core/services/websocket.service';
import { TradingService } from '../../../core/services/trading.service';
import { NavUsageService } from '../../../core/services/nav-usage.service';
import { NotificationCenterService } from '../../../core/services/notification-center.service';
import { NotificationDropdownComponent } from './notification-dropdown/notification-dropdown.component';
import { UserDropdownComponent } from './user-dropdown/user-dropdown.component';

@Component({
  selector: 'app-default-header',
  templateUrl: './default-header.component.html',
  styleUrl: './default-header.component.scss',
  imports: [
    ContainerComponent, HeaderTogglerDirective, SidebarToggleDirective,
    IconDirective, HeaderNavComponent, NavItemComponent, NavLinkDirective,
    RouterLink, RouterLinkActive, NgTemplateOutlet,
    DropdownComponent, DropdownToggleDirective, DropdownMenuDirective,
    DropdownItemDirective, TooltipDirective, NotificationDropdownComponent, UserDropdownComponent,
    DecimalPipe
  ]
})
export class DefaultHeaderComponent extends HeaderComponent {

  readonly #colorModeService = inject(ColorModeService);
  readonly #ws = inject(WebSocketService);
  readonly #trading = inject(TradingService);
  readonly #navUsage = inject(NavUsageService);
  readonly #notifCenter = inject(NotificationCenterService);
  readonly #destroyRef = inject(DestroyRef);
  readonly colorMode = this.#colorModeService.colorMode;
  readonly wsConnected = this.#ws.connected;
  readonly topLinks = this.#navUsage.topLinks;

  // Price source tracking
  readonly isMockPrices = this.#ws.isMockPrices;
  readonly pricesAreFresh = this.#ws.pricesAreFresh;
  readonly brokerReconnectAttempts = this.#ws.brokerReconnectAttempts;
  readonly brokerMaxReconnectAttempts = this.#ws.brokerMaxReconnectAttempts;

  // Real-time P&L (computed from live prices + open positions)
  readonly livePnl = computed(() => {
    const positions = this.#trading.paperPositions();
    const prices = this.#ws.prices();
    if (!positions.length) return 0;
    return positions.reduce((sum, pos) => {
      const tick = prices[pos.epic];
      if (!tick) return sum;
      const current = pos.direction === 'BUY' ? tick.bid : tick.offer;
      const diff = pos.direction === 'BUY'
        ? current - pos.level
        : pos.level - current;
      return sum + Math.round(diff * pos.size * 100) / 100;
    }, 0);
  });
  readonly openPositionCount = computed(() => this.#trading.paperPositions().length);
  readonly dailyPnl = computed(() => this.#trading.overview()?.today_realized_pnl ?? null);

  readonly colorModes = [
    { name: 'light', text: 'Light', icon: 'cilSun' },
    { name: 'dark', text: 'Dark', icon: 'cilMoon' },
    { name: 'auto', text: 'Auto', icon: 'cilContrast' }
  ];

  readonly icons = computed(() => {
    const currentMode = this.colorMode();
    return this.colorModes.find(mode => mode.name === currentMode)?.icon ?? 'cilSun';
  });

  constructor() {
    super();
    this.#notifCenter.init();

    // Load overview immediately + refresh every 60s for daily P&L
    this.#trading.loadOverview();
    const interval = setInterval(() => this.#trading.loadOverview(), 60_000);
    this.#destroyRef.onDestroy(() => clearInterval(interval));
  }

  sidebarId = input('sidebar1');
}
