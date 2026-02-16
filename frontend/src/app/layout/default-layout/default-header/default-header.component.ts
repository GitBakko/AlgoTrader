import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, inject, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import {
  BreadcrumbRouterComponent,
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
import { UserDropdownComponent } from './user-dropdown/user-dropdown.component';

@Component({
  selector: 'app-default-header',
  templateUrl: './default-header.component.html',
  styleUrl: './default-header.component.scss',
  imports: [
    ContainerComponent, HeaderTogglerDirective, SidebarToggleDirective,
    IconDirective, HeaderNavComponent, NavItemComponent, NavLinkDirective,
    RouterLink, RouterLinkActive, NgTemplateOutlet, BreadcrumbRouterComponent,
    DropdownComponent, DropdownToggleDirective, DropdownMenuDirective,
    DropdownItemDirective, TooltipDirective, UserDropdownComponent
  ]
})
export class DefaultHeaderComponent extends HeaderComponent {

  readonly #colorModeService = inject(ColorModeService);
  readonly #ws = inject(WebSocketService);
  readonly colorMode = this.#colorModeService.colorMode;
  readonly wsConnected = this.#ws.connected;

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
  }

  sidebarId = input('sidebar1');
}
