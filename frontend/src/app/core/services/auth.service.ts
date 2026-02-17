import { Injectable, inject, signal, computed, effect } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap, catchError, throwError, of } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  User,
  LoginRequest,
  LoginResponse,
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
      } catch (error) {
        console.error('[AuthService] Failed to parse stored user data', error);
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
        }),
        catchError(error => {
          console.error('[AuthService] Login failed', error);
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
          console.error('[AuthService] Registration failed', error);
          return throwError(() => error);
        })
      );
  }

  /**
   * Logout and clear authentication state
   */
  logout(): void {
    this.clearAuth();
    this.router.navigate(['/login']);
  }

  /**
   * Clear all authentication data
   */
  private clearAuth(): void {
    this.authState.set({
      isAuthenticated: false,
      currentUser: null,
      token: null
    });
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
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
          console.error('[AuthService] Failed to get current user', error);
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
          console.error('[AuthService] Failed to upload avatar', error);
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
          console.error('[AuthService] Failed to delete avatar', error);
          return throwError(() => error);
        })
      );
  }
}
