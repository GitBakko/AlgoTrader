import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ApiResponse } from '../models';

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
      .pipe(map(res => res.data));
  }

  post<T>(path: string, body?: unknown): Observable<T> {
    return this.http
      .post<ApiResponse<T>>(`${this.baseUrl}${path}`, body)
      .pipe(map(res => res.data));
  }

  put<T>(path: string, body?: unknown): Observable<T> {
    return this.http
      .put<ApiResponse<T>>(`${this.baseUrl}${path}`, body)
      .pipe(map(res => res.data));
  }

  /** H4-FE-AUDIT: added so notification-center and similar services can
   *  delete via the unified envelope-unwrapping pipeline. */
  delete<T>(path: string, params?: Params): Observable<T> {
    return this.http
      .delete<ApiResponse<T>>(`${this.baseUrl}${path}`, { params: buildParams(params) })
      .pipe(map(res => res.data));
  }

  getBlob(path: string, params?: Params): Observable<Blob> {
    return this.http.get(`${this.baseUrl}${path}`, {
      params: buildParams(params),
      responseType: 'blob',
    });
  }
}
