import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Authentication Interceptor
 * Attaches JWT token to all HTTP requests and handles authentication errors
 * MANTIS AI - Secure API communication
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const token = authService.getToken();

  // Clone request and add authorization header if token exists
  let authReq = req;
  if (token) {
    authReq = req.clone({
      setHeaders: {
        Authorization: `Bearer ${token}`
      }
    });
  }

  return next(authReq).pipe(
    catchError((error) => {
      // Handle 401 Unauthorized - token expired or invalid
      if (error.status === 401) {
        console.error('[AuthInterceptor] 401 Unauthorized - logging out');
        authService.logout();
      }

      // Handle 403 Forbidden - insufficient permissions
      if (error.status === 403) {
        console.error('[AuthInterceptor] 403 Forbidden - insufficient permissions');
        // You could show a toast/notification here
        const message = error?.error?.error || 'Permessi insufficienti per eseguire questa operazione';
        console.warn('[AuthInterceptor] Permission denied:', message);
      }

      return throwError(() => error);
    })
  );
};
