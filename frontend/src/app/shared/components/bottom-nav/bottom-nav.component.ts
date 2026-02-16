import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { SidebarService } from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';

@Component({
  selector: 'app-bottom-nav',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, IconDirective],
  template: `
    <nav class="bottom-nav d-lg-none">
      <a class="bottom-nav__item" routerLink="/dashboard" routerLinkActive="bottom-nav__item--active">
        <svg cIcon name="cilSpeedometer" size="lg"></svg>
        <span class="bottom-nav__label">Home</span>
      </a>
      <a class="bottom-nav__item" routerLink="/positions" routerLinkActive="bottom-nav__item--active">
        <svg cIcon name="cilLayers" size="lg"></svg>
        <span class="bottom-nav__label">Posizioni</span>
      </a>
      <a class="bottom-nav__item" routerLink="/markets" routerLinkActive="bottom-nav__item--active">
        <svg cIcon name="cilChartLine" size="lg"></svg>
        <span class="bottom-nav__label">Mercati</span>
      </a>
      <a class="bottom-nav__item" routerLink="/signals" routerLinkActive="bottom-nav__item--active">
        <svg cIcon name="cilBolt" size="lg"></svg>
        <span class="bottom-nav__label">Segnali</span>
      </a>
      <button class="bottom-nav__item" (click)="openMenu()" type="button">
        <svg cIcon name="cilMenu" size="lg"></svg>
        <span class="bottom-nav__label">Menu</span>
      </button>
    </nav>
  `
})
export class BottomNavComponent {
  private readonly sidebarService = inject(SidebarService);

  openMenu(): void {
    this.sidebarService.toggle({ id: 'sidebar1', visible: 'toggle' });
  }
}
