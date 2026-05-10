import { HttpErrorResponse, HttpEvent, HttpHandlerFn, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, catchError, filter, switchMap, take, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Authentication Interceptor
 * Attaches JWT token to all HTTP requests.
 * On 401: attempts silent token refresh, then retries the original request.
 * Uses BehaviorSubject to queue concurrent requests during refresh.
 *
 * C3-FE security fix: refresh-state used to live at module scope, so
 * `isRefreshing=true` (or queued subscriptions) could survive a logout
 * and bleed into the next session — old-session subscribers replaying
 * old requests under new credentials, or new-session 401s queueing
 * forever. The state now lives in module-level mutable refs but is
 * explicitly reset by `resetAuthInterceptorState()` which is called
 * from `AuthService.clearAuth()`.
 */

let isRefreshing = false;
let refreshTokenSubject = new BehaviorSubject<string | null>(null);

/** Reset interceptor state on logout/login boundary. Called from
 *  AuthService.clearAuth so every new session starts clean. */
export function resetAuthInterceptorState(): void {
  isRefreshing = false;
  // Complete the existing subject so any queued subscribers terminate
  // with a finite-stream rather than emitting against a new session.
  try {
    refreshTokenSubject.complete();
  } catch {
    /* noop */
  }
  refreshTokenSubject = new BehaviorSubject<string | null>(null);
}

function addToken(req: HttpRequest<unknown>, token: string): HttpRequest<unknown> {
  return req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const token = authService.getToken();

  const authReq = token ? addToken(req, token) : req;

  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !req.url.includes('/api/auth/refresh') && !req.url.includes('/api/auth/login')) {
        return handle401(req, next, authService, router);
      }

      if (error.status === 403) {
        console.warn('[AuthInterceptor] 403 Forbidden - insufficient permissions');
      }

      return throwError(() => error);
    })
  );
};

function handle401(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  authService: AuthService,
  router: Router
): Observable<HttpEvent<unknown>> {
  if (!isRefreshing) {
    isRefreshing = true;
    refreshTokenSubject.next(null);

    return authService.refreshAccessToken().pipe(
      switchMap(response => {
        isRefreshing = false;
        const newToken = response.data.access_token;
        refreshTokenSubject.next(newToken);
        return next(addToken(req, newToken));
      }),
      catchError(err => {
        isRefreshing = false;
        refreshTokenSubject.next(null);
        authService.clearAuth();
        router.navigate(['/login']);
        return throwError(() => err);
      })
    );
  }

  // Another request came in while refreshing — wait for the new token
  return refreshTokenSubject.pipe(
    filter(token => token !== null),
    take(1),
    switchMap(token => next(addToken(req, token!)))
  );
}
