import { Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { NgScrollbar } from 'ngx-scrollbar';

import {
  ContainerComponent,
  ShadowOnScrollDirective,
  SidebarBrandComponent,
  SidebarComponent,
  SidebarFooterComponent,
  SidebarHeaderComponent,
  SidebarNavComponent,
  SidebarToggleDirective,
  SidebarTogglerDirective
} from '@coreui/angular';

import { DefaultFooterComponent, DefaultHeaderComponent } from './';
import { ToastContainerComponent } from '../../shared/components/toast-container/toast-container.component';
import { ConfirmDialogComponent } from '../../shared/components/confirm-dialog/confirm-dialog.component';
import { BottomNavComponent } from '../../shared/components/bottom-nav/bottom-nav.component';
import { SignalAuditDrawerComponent } from '../../shared/components/signal-audit-drawer/signal-audit-drawer.component';
import { navItems } from './_nav';
import { WebSocketService } from '../../core/services/websocket.service';

@Component({
  selector: 'app-dashboard',
  templateUrl: './default-layout.component.html',
  styleUrls: ['./default-layout.component.scss'],
  imports: [
    SidebarComponent,
    SidebarHeaderComponent,
    SidebarBrandComponent,
    SidebarNavComponent,
    SidebarFooterComponent,
    SidebarToggleDirective,
    SidebarTogglerDirective,
    ContainerComponent,
    DefaultFooterComponent,
    DefaultHeaderComponent,
    NgScrollbar,
    RouterOutlet,
    RouterLink,
    ShadowOnScrollDirective,
    ToastContainerComponent,
    ConfirmDialogComponent,
    BottomNavComponent,
    SignalAuditDrawerComponent,
  ]
})
export class DefaultLayoutComponent {
  public navItems = [...navItems];

  private readonly ws = inject(WebSocketService);

  constructor() {
    // Connect to trade WebSocket — toast notifications handled by NotificationService
    this.ws.connectTrades();
  }
}
