import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, inject, input } from '@angular/core';
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
    DropdownItemDirective, TooltipDirective, NotificationDropdownComponent, UserDropdownComponent
  ]
})
export class DefaultHeaderComponent extends HeaderComponent {

  readonly #colorModeService = inject(ColorModeService);
  readonly #ws = inject(WebSocketService);
  readonly #navUsage = inject(NavUsageService);
  readonly #notifCenter = inject(NotificationCenterService);
  readonly colorMode = this.#colorModeService.colorMode;
  readonly wsConnected = this.#ws.connected;
  readonly topLinks = this.#navUsage.topLinks;

  // Price source tracking
  readonly isMockPrices = this.#ws.isMockPrices;
  readonly brokerReconnectAttempts = this.#ws.brokerReconnectAttempts;
  readonly brokerMaxReconnectAttempts = this.#ws.brokerMaxReconnectAttempts;

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
  }

  sidebarId = input('sidebar1');
}
