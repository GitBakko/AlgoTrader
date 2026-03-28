import { Injectable, inject, signal, computed, effect } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap, catchError, throwError, of } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  User,
  LoginRequest,
  LoginResponse,
  RefreshResponse,
  RegisterRequest,
  RegisterResponse,
  AuthState
} from '../models/auth.models';
import { ApiResponse } from '../models';

/**
 * Authentication Service
 * Manages user authentication, authorization, and session state using Angular Signals
 * MANTIS AI - Secure trading platform authentication
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly baseUrl = environment.apiUrl;
  private readonly TOKEN_KEY = 'mantis_auth_token';
  private readonly USER_KEY = 'mantis_current_user';
  private readonly REFRESH_TOKEN_KEY = 'mantis_refresh_token';

  // Reactive state with Angular Signals
  private readonly authState = signal<AuthState>({
    isAuthenticated: false,
    currentUser: null,
    token: null
  });

  // Public computed signals
  readonly isAuthenticated = computed(() => this.authState().isAuthenticated);
  readonly currentUser = computed(() => this.authState().currentUser);
  readonly token = computed(() => this.authState().token);

  constructor() {
    // Initialize state from localStorage on service creation
    this.loadStoredAuth();

    // Auto-save to localStorage on state changes
    effect(() => {
      const state = this.authState();
      if (state.token) {
        localStorage.setItem(this.TOKEN_KEY, state.token);
      } else {
        localStorage.removeItem(this.TOKEN_KEY);
      }
      if (state.currentUser) {
        localStorage.setItem(this.USER_KEY, JSON.stringify(state.currentUser));
      } else {
        localStorage.removeItem(this.USER_KEY);
      }
    });
  }

  /**
   * Load authentication state from localStorage
   */
  private loadStoredAuth(): void {
    const token = localStorage.getItem(this.TOKEN_KEY);
    const userJson = localStorage.getItem(this.USER_KEY);

    if (token && userJson) {
      try {
        const user = JSON.parse(userJson) as User;
        this.authState.set({
          isAuthenticated: true,
          currentUser: user,
          token
        });
        // Refresh profile in background to get latest avatar_url
        // Deferred to avoid circular dependency: AuthService constructor → HTTP → authInterceptor → inject(AuthService)
        queueMicrotask(() => this.getCurrentUser().subscribe());
      } catch (error) {
        this.clearAuth();
      }
    }
  }

  /**
   * Login with username and password
   */
  login(username: string, password: string): Observable<ApiResponse<LoginResponse>> {
    const request: LoginRequest = { username, password };

    return this.http.post<ApiResponse<LoginResponse>>(`${this.baseUrl}/api/auth/login`, request)
      .pipe(
        tap(response => {
          const data = response.data;
          this.authState.set({
            isAuthenticated: true,
            currentUser: data.user,
            token: data.access_token
          });
          if (data.refresh_token) {
            localStorage.setItem(this.REFRESH_TOKEN_KEY, data.refresh_token);
          }
        }),
        catchError(error => {
          return throwError(() => error);
        })
      );
  }

  /**
   * Register a new user
   */
  register(username: string, email: string, password: string, role_name: string = 'VIEWER'): Observable<ApiResponse<RegisterResponse>> {
    const request: RegisterRequest = { username, email, password, role_name };

    return this.http.post<ApiResponse<RegisterResponse>>(`${this.baseUrl}/api/auth/register`, request)
      .pipe(
        tap(() => {}),
        catchError(error => {
          return throwError(() => error);
        })
      );
  }

  /**
   * Logout and clear authentication state
   */
  logout(): void {
    // Best-effort backend logout (revoke refresh tokens), don't block on failure
    this.http.post(`${this.baseUrl}/api/auth/logout`, {}).pipe(
      catchError(() => of(null))
    ).subscribe(() => {
      this.clearAuth();
      this.router.navigate(['/login']);
    });
  }

  /**
   * Clear all authentication data
   */
  clearAuth(): void {
    this.authState.set({
      isAuthenticated: false,
      currentUser: null,
      token: null
    });
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    localStorage.removeItem(this.REFRESH_TOKEN_KEY);
  }

  /**
   * Get current user profile from backend
   */
  getCurrentUser(): Observable<ApiResponse<User>> {
    return this.http.get<ApiResponse<User>>(`${this.baseUrl}/api/auth/me`)
      .pipe(
        tap(response => {
          const user = response.data;
          this.authState.update(state => ({
            ...state,
            currentUser: user
          }));
          // Profile refreshed
        }),
        catchError(error => {
          if (error.status === 401) {
            this.logout();
          }
          return throwError(() => error);
        })
      );
  }

  /**
   * Get stored token
   */
  getToken(): string | null {
    return this.token();
  }

  /**
   * Get stored refresh token
   */
  getRefreshToken(): string | null {
    return localStorage.getItem(this.REFRESH_TOKEN_KEY);
  }

  /**
   * Refresh access token using the stored refresh token.
   * Updates auth state with new tokens on success.
   */
  refreshAccessToken(): Observable<ApiResponse<RefreshResponse>> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      return throwError(() => new Error('No refresh token available'));
    }

    return this.http.post<ApiResponse<RefreshResponse>>(
      `${this.baseUrl}/api/auth/refresh`,
      { refresh_token: refreshToken }
    ).pipe(
      tap(response => {
        const data = response.data;
        this.authState.update(state => ({
          ...state,
          token: data.access_token,
          isAuthenticated: true
        }));
        localStorage.setItem(this.REFRESH_TOKEN_KEY, data.refresh_token);
      }),
      catchError(error => {
        return throwError(() => error);
      })
    );
  }

  /**
   * Check if user has a specific permission
   */
  hasPermission(resource: string, action: string): boolean {
    const user = this.currentUser();
    if (!user || !user.permissions) {
      return false;
    }

    return user.permissions.some(
      p => p.resource === resource && p.action === action
    );
  }

  /**
   * Check if user has any of the specified permissions
   */
  hasAnyPermission(permissions: Array<{ resource: string; action: string }>): boolean {
    return permissions.some(p => this.hasPermission(p.resource, p.action));
  }

  /**
   * Check if user has all of the specified permissions
   */
  hasAllPermissions(permissions: Array<{ resource: string; action: string }>): boolean {
    return permissions.every(p => this.hasPermission(p.resource, p.action));
  }

  /**
   * Check if token is expired (basic check, backend will validate)
   */
  isTokenExpired(): boolean {
    // For now, rely on backend validation via 401 responses
    // Could be enhanced with JWT decoding and expiry checking
    return false;
  }

  /**
   * Refresh user permissions from backend
   */
  refreshPermissions(): Observable<ApiResponse<User>> {
    return this.getCurrentUser();
  }

  /**
   * Upload user avatar image
   */
  uploadAvatar(file: File): Observable<ApiResponse<User>> {
    const formData = new FormData();
    formData.append('file', file);

    return this.http.post<ApiResponse<User>>(`${this.baseUrl}/api/auth/avatar/upload`, formData)
      .pipe(
        tap(response => {
          const updatedUser = response.data;
          this.authState.update(state => ({
            ...state,
            currentUser: updatedUser
          }));
          // Avatar uploaded
        }),
        catchError(error => {
          return throwError(() => error);
        })
      );
  }

  /**
   * Delete user avatar image
   */
  deleteAvatar(): Observable<ApiResponse<{ message: string }>> {
    return this.http.delete<ApiResponse<{ message: string }>>(`${this.baseUrl}/api/auth/avatar`)
      .pipe(
        tap(() => {
          // Update user state to remove avatar
          this.authState.update(state => ({
            ...state,
            currentUser: state.currentUser ? {
              ...state.currentUser,
              avatar_url: null
            } : null
          }));
          // Avatar deleted
        }),
        catchError(error => {
          return throwError(() => error);
        })
      );
  }
}
