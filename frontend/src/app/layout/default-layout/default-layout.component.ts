import { Component, effect, inject, signal } from '@angular/core';
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
import { BottomNavComponent } from '../../shared/components/bottom-nav/bottom-nav.component';
import { navItems } from './_nav';
import { WebSocketService } from '../../core/services/websocket.service';
import { ToastService } from '../../shared/services/toast.service';

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
    BottomNavComponent
  ]
})
export class DefaultLayoutComponent {
  public navItems = [...navItems];

  private readonly ws = inject(WebSocketService);
  private readonly toast = inject(ToastService);
  private readonly lastSeenTradeId = signal<string | null>(null);

  constructor() {
    this.ws.connectTrades();

    effect(() => {
      const trade = this.ws.lastTrade();
      if (!trade) return;

      // Skip duplicate events on reconnect
      if (trade.deal_id === this.lastSeenTradeId()) return;
      this.lastSeenTradeId.set(trade.deal_id);

      if (trade.event === 'OPEN') {
        const dir = trade.direction === 'BUY' ? '▲ BUY' : '▼ SELL';
        this.toast.info(`${dir} ${trade.epic} aperto`, 5000);
      } else if (trade.event === 'CLOSE') {
        const pnl = trade.pnl ?? 0;
        const reason = (trade.close_reason ?? '').toLowerCase();
        const isSL = reason.includes('stop') || reason.includes('sl');
        const isTP = reason.includes('profit') || reason.includes('tp');
        const pnlStr = `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`;

        if (isSL && pnl < 0) {
          this.toast.error(`Stop Loss: ${trade.epic} ${pnlStr} USD`, 6000);
        } else if (isTP && pnl > 0) {
          this.toast.success(`Take Profit: ${trade.epic} ${pnlStr} USD`, 5000);
        } else if (pnl >= 0) {
          this.toast.success(`${trade.epic} chiuso: ${pnlStr} USD`, 5000);
        } else {
          this.toast.warning(`${trade.epic} chiuso: ${pnlStr} USD`, 5000);
        }
      }
    });
  }
}
