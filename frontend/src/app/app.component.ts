import { Component, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Title } from '@angular/platform-browser';
import { ActivatedRoute, NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { delay, filter, map, tap } from 'rxjs/operators';

import { ColorModeService } from '@coreui/angular';
import { IconSetService } from '@coreui/icons-angular';
import { iconSubset } from './icons/icon-subset';
import { WebSocketService } from './core/services/websocket.service';
import { NotificationService } from './shared/services/notification.service';
import { AuthService } from './core/services/auth.service';
import { NotificationCenterService } from './core/services/notification-center.service';

@Component({
    selector: 'app-root',
    template: '<router-outlet />',
    imports: [RouterOutlet]
})
export class AppComponent implements OnInit {
  title = 'MANTIS AI';

  readonly #destroyRef: DestroyRef = inject(DestroyRef);
  readonly #activatedRoute: ActivatedRoute = inject(ActivatedRoute);
  readonly #router = inject(Router);
  readonly #titleService = inject(Title);

  readonly #colorModeService = inject(ColorModeService);
  readonly #iconSetService = inject(IconSetService);
  readonly #ws = inject(WebSocketService);
  readonly #notifications = inject(NotificationService);
  readonly #authService = inject(AuthService);
  readonly #notifCenter = inject(NotificationCenterService);

  constructor() {
    this.#titleService.setTitle(this.title);
    // iconSet singleton
    this.#iconSetService.icons = { ...iconSubset };
    this.#colorModeService.localStorageItemName.set('mantis-theme');
    this.#colorModeService.eventName.set('ColorSchemeChange');
    // Default to dark mode
    if (!localStorage.getItem('mantis-theme')) {
      this.#colorModeService.colorMode.set('dark');
    }
  }

  ngOnInit(): void {
    // C1-FE-AUDIT: wire AuthService logout teardown so clearAuth() actually
    // disconnects both WebSockets. Without this call, the lazy refs in
    // AuthService stay null and the WS auto-reconnects after logout.
    this.#authService.registerLogoutTeardown({
      ws: this.#ws,
      notif: this.#notifCenter,
    });

    // Connect WebSocket channels for real-time prices and trade events
    this.#ws.connectPrices();
    this.#ws.connectTrades();

    // Initialize browser notifications for trade events
    this.#notifications.requestPermission().catch(() => {});
    this.#notifications.init();

    this.#router.events.pipe(
        takeUntilDestroyed(this.#destroyRef)
      ).subscribe((evt) => {
      if (!(evt instanceof NavigationEnd)) {
        return;
      }
    });

    this.#activatedRoute.queryParams
      .pipe(
        delay(1),
        map(params => <string>params['theme']?.match(/^[A-Za-z0-9\s]+/)?.[0]),
        filter(theme => ['dark', 'light', 'auto'].includes(theme)),
        tap(theme => {
          this.#colorModeService.colorMode.set(theme);
        }),
        takeUntilDestroyed(this.#destroyRef)
      )
      .subscribe();
  }
}
