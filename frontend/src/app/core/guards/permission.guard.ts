import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { AuthService } from '../services/auth.service';

/**
 * Permission Guard
 * Protects routes by checking if user has required permissions
 * Usage: canActivate: [permissionGuard], data: { resource: 'trading', action: 'execute' }
 * MANTIS AI - Fine-grained authorization
 */
export const permissionGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  // Check if user is authenticated first
  if (!authService.isAuthenticated()) {
    console.warn('[PermissionGuard] User not authenticated, redirecting to login');
    router.navigate(['/login'], { queryParams: { returnUrl: state.url } });
    return false;
  }

  // Get required permission from route data
  const resource = route.data['resource'] as string | undefined;
  const action = route.data['action'] as string | undefined;

  if (!resource || !action) {
    // L1-FE-AUDIT: was fail-open (return true) — a developer adding
    // `canActivate: [permissionGuard]` without route data silently
    // gained unrestricted access. Now fail-closed: deny + redirect to
    // /403 so the misconfiguration is visible.
    console.error('[PermissionGuard] Route missing resource/action — denying access');
    router.navigate(['/403']);
    return false;
  }

  // Check if user has the required permission
  const hasPermission = authService.hasPermission(resource, action);

  if (hasPermission) {
    return true;
  }

  console.warn(
    `[PermissionGuard] User does not have permission: ${resource}:${action}`
  );

  // Redirect to 403 forbidden page or dashboard
  router.navigate(['/403']);
  return false;
};

/**
 * Multiple Permissions Guard
 * Checks if user has ALL specified permissions
 * Usage: canActivate: [allPermissionsGuard], data: { permissions: [{resource: 'trading', action: 'execute'}] }
 */
export const allPermissionsGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (!authService.isAuthenticated()) {
    router.navigate(['/login'], { queryParams: { returnUrl: state.url } });
    return false;
  }

  const permissions = route.data['permissions'] as Array<{ resource: string; action: string }> | undefined;

  if (!permissions || permissions.length === 0) {
    return true;
  }

  const hasAllPermissions = authService.hasAllPermissions(permissions);

  if (hasAllPermissions) {
    return true;
  }

  console.warn('[AllPermissionsGuard] User missing required permissions', permissions);
  router.navigate(['/403']);
  return false;
};

/**
 * Any Permission Guard
 * Checks if user has AT LEAST ONE of the specified permissions
 * Usage: canActivate: [anyPermissionGuard], data: { permissions: [{resource: 'trading', action: 'read'}] }
 */
export const anyPermissionGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (!authService.isAuthenticated()) {
    router.navigate(['/login'], { queryParams: { returnUrl: state.url } });
    return false;
  }

  const permissions = route.data['permissions'] as Array<{ resource: string; action: string }> | undefined;

  if (!permissions || permissions.length === 0) {
    return true;
  }

  const hasAnyPermission = authService.hasAnyPermission(permissions);

  if (hasAnyPermission) {
    return true;
  }

  console.warn('[AnyPermissionGuard] User has none of the required permissions', permissions);
  router.navigate(['/403']);
  return false;
};
