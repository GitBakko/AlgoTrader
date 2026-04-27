import { ApplicationConfig, APP_INITIALIZER, LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeIt from '@angular/common/locales/it';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';

registerLocaleData(localeIt, 'it-IT');
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import {
  PreloadAllModules,
  provideRouter,
  withEnabledBlockingInitialNavigation,
  withHashLocation,
  withInMemoryScrolling,
  withPreloading,
  withRouterConfig
} from '@angular/router';
import { IconSetService } from '@coreui/icons-angular';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { errorInterceptor } from './core/interceptors/error.interceptor';
import { LogoService } from './core/services/logo.service';

/**
 * Warm the asset logo cache on app initialization.
 *
 * `LogoService.getLogoUrls` resolves a static fallback chain
 * synchronously and persists it in localStorage, so this just walks the
 * asset universe once to avoid a render-time miss on the first card.
 */
function initializeLogos(logoService: LogoService) {
  const allEpics = [
    'BTCUSD', 'ETHUSD', 'SOLUSD', 'BNBUSD', 'DOGUSD', 'DASHUSD', 'ICPUSD',
    'NVDA', 'TSLA',
    'XAUUSD', 'XAGUSD', 'WTIUSD', 'NATGAS', 'COPPER', 'PLATINUM',
    'EURUSD', 'GBPUSD', 'USDJPY',
    'US500', 'NAS100', 'DE40',
  ];
  return () => {
    for (const epic of allEpics) {
      logoService.getLogoUrls(epic);
    }
  };
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes,
      withRouterConfig({
        onSameUrlNavigation: 'reload'
      }),
      withInMemoryScrolling({
        scrollPositionRestoration: 'top',
        anchorScrolling: 'enabled'
      }),
      withEnabledBlockingInitialNavigation(),
      withHashLocation(),
      withPreloading(PreloadAllModules)
    ),
    provideHttpClient(
      withFetch(),
      withInterceptors([authInterceptor, errorInterceptor])
    ),
    IconSetService,
    { provide: LOCALE_ID, useValue: 'it-IT' },
    provideAnimationsAsync(),
    {
      provide: APP_INITIALIZER,
      useFactory: initializeLogos,
      deps: [LogoService],
      multi: true
    }
  ]
};
