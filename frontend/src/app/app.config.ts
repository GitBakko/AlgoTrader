import { ApplicationConfig, APP_INITIALIZER } from '@angular/core';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
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
 * Preload all asset logos on app initialization
 */
function initializeLogos(logoService: LogoService) {
  return () => logoService.preloadAll();
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
    provideAnimationsAsync(),
    {
      provide: APP_INITIALIZER,
      useFactory: initializeLogos,
      deps: [LogoService],
      multi: true
    }
  ]
};
