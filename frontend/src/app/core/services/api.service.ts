import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map, OperatorFunction } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ApiResponse } from '../models';

/**
 * Unwraps the standard envelope `{success, data, error?}` returned by every
 * backend route.  When `success === false` at HTTP 200 the error string was
 * previously swallowed and callers received `undefined as T` into their
 * signals — the error message simply vanished (audit M1.10).
 */
function unwrap<T>(): OperatorFunction<ApiResponse<T>, T> {
  return map((res: ApiResponse<T>) => {
    if (res && res.success === false) {
      // Surface envelope failures arriving at HTTP 200 — silently returning
      // res.data fed `undefined as T` into signals (audit M1.10).
      throw new Error(res.error || 'API returned success:false');
    }
    return res.data;
  });
}

/**
 * ApiService — single entry point for all backend HTTP traffic.
 *
 * H4-FE-AUDIT / H1-CORE: every other service should call here instead of
 * injecting HttpClient directly so that cross-cutting concerns
 * (interceptor coverage, envelope unwrapping, future header injection)
 * remain centralised. AuthService is the documented exception (DI cycle
 * via the auth interceptor).
 *
 * M2-FE-AUDIT: param coercion now goes through HttpParams build instead
 * of `params as any`. Booleans are preserved via `String(v)` so call
 * sites that pass `is_read: true` produce `?is_read=true` reliably.
 */

type ParamValue = string | number | boolean;
type Params = Record<string, ParamValue | null | undefined>;

function buildParams(params?: Params): HttpParams | undefined {
  if (!params) return undefined;
  let httpParams = new HttpParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    httpParams = httpParams.set(key, String(value));
  }
  return httpParams;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  get<T>(path: string, params?: Params): Observable<T> {
    return this.http
      .get<ApiResponse<T>>(`${this.baseUrl}${path}`, { params: buildParams(params) })
      .pipe(unwrap<T>());
  }

  post<T>(path: string, body?: unknown): Observable<T> {
    return this.http
      .post<ApiResponse<T>>(`${this.baseUrl}${path}`, body)
      .pipe(unwrap<T>());
  }

  put<T>(path: string, body?: unknown): Observable<T> {
    return this.http
      .put<ApiResponse<T>>(`${this.baseUrl}${path}`, body)
      .pipe(unwrap<T>());
  }

  /** H4-FE-AUDIT: added so notification-center and similar services can
   *  delete via the unified envelope-unwrapping pipeline. */
  delete<T>(path: string, params?: Params): Observable<T> {
    return this.http
      .delete<ApiResponse<T>>(`${this.baseUrl}${path}`, { params: buildParams(params) })
      .pipe(unwrap<T>());
  }

  getBlob(path: string, params?: Params): Observable<Blob> {
    return this.http.get(`${this.baseUrl}${path}`, {
      params: buildParams(params),
      responseType: 'blob',
    });
  }
}
