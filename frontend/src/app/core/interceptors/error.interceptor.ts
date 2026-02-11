import { HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  return next(req).pipe(
    catchError((error) => {
      const message = error?.error?.error || error?.message || 'Unknown error';
      console.error(`[API Error] ${req.method} ${req.url}: ${message}`);
      return throwError(() => error);
    })
  );
};
