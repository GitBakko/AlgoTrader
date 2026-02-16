import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { AuthService } from '../services/auth.service';

/**
 * Authentication Guard
 * Protects routes by checking if user is authenticated
 * MANTIS AI - Secure route protection
 */
export const authGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    return true;
  }

  console.warn('[AuthGuard] User not authenticated, redirecting to login');
  // Store the attempted URL for redirecting after login
  const returnUrl = state.url;
  router.navigate(['/login'], { queryParams: { returnUrl } });
  return false;
};
