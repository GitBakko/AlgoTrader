import { HttpInterceptorFn, HttpRequest, HttpHandlerFn, HttpErrorResponse, HttpEvent } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError, timer, switchMap, Observable } from 'rxjs';
import { ToastService } from '../../shared/services/toast.service';

const AUTH_ENDPOINTS = ['/api/auth/login', '/api/auth/register', '/api/auth/refresh'];
const RETRYABLE_STATUSES = new Set([0, 502, 503]);
const MAX_RETRIES = 3;

// Only idempotent reads are safe to replay: status 0 covers "request sent
// but response lost" — re-sending a POST can duplicate an order/backtest
// (audit M1.10).
const RETRYABLE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

function shouldSkipToast(url: string, status: number): boolean {
  if (status === 401) return true;
  if (AUTH_ENDPOINTS.some(ep => url.includes(ep))) return true;
  return false;
}

function getFriendlyMessage(status: number, detail: string): string {
  switch (status) {
    case 0:   return 'Connessione al server non disponibile. Controlla la rete.';
    case 400: return detail || 'Richiesta non valida.';
    case 403: return 'Permessi insufficienti per questa operazione.';
    case 404: return 'Risorsa non trovata.';
    case 422: return detail || 'Dati non validi.';
    case 429: return 'Troppe richieste. Attendi qualche secondo.';
    case 500: return 'Errore interno del server. Riprova più tardi.';
    case 502:
    case 503: return 'Server temporaneamente non disponibile.';
    default:  return detail || `Errore ${status}`;
  }
}

function withRetry(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  attempt: number,
  toast: ToastService
): Observable<HttpEvent<unknown>> {
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      const status = error.status ?? 0;
      const detail: string = error?.error?.error || error?.message || '';

      if (
        RETRYABLE_METHODS.has(req.method) &&
        RETRYABLE_STATUSES.has(status) &&
        attempt < MAX_RETRIES
      ) {
        const delay = Math.pow(2, attempt) * 1000;
        return timer(delay).pipe(
          switchMap(() => withRetry(req, next, attempt + 1, toast))
        );
      }

      if (!shouldSkipToast(req.url, status)) {
        const message = getFriendlyMessage(status, detail);
        if (status >= 500 || status === 0) {
          toast.error(message);
        } else {
          toast.warning(message);
        }
      }

      console.error(`[API Error] ${req.method} ${req.url} (${status}): ${detail}`);
      return throwError(() => error);
    })
  );
}

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(ToastService);
  return withRetry(req, next, 0, toast);
};
