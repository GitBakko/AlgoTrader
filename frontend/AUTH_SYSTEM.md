# MANTIS AI - Authentication & Authorization System

## Overview

Complete authentication and authorization system for the MANTIS AI Angular 21 frontend with JWT token-based authentication, role-based access control (RBAC), and fine-grained permissions.

## Architecture

### Core Components

1. **AuthService** (`src/app/core/services/auth.service.ts`)
   - Manages authentication state using Angular Signals
   - Handles login, registration, and logout
   - Stores JWT tokens in localStorage
   - Provides permission checking methods

2. **Auth Interceptor** (`src/app/core/interceptors/auth.interceptor.ts`)
   - Automatically attaches JWT token to all HTTP requests
   - Handles 401 (Unauthorized) and 403 (Forbidden) responses
   - Triggers logout on authentication failures

3. **Auth Guard** (`src/app/core/guards/auth.guard.ts`)
   - Protects routes requiring authentication
   - Redirects unauthenticated users to login page
   - Preserves return URL for post-login navigation

4. **Permission Guard** (`src/app/core/guards/permission.guard.ts`)
   - Protects routes requiring specific permissions
   - Three variants: `permissionGuard`, `allPermissionsGuard`, `anyPermissionGuard`
   - Redirects to 403 page if user lacks permissions

### UI Components

1. **Login Component** (`src/app/views/pages/login/`)
   - Reactive form with validation
   - MANTIS AI branding (neon green theme)
   - Loading states and error handling
   - Remember me functionality

2. **Register Component** (`src/app/views/pages/register/`)
   - User registration with role selection
   - Password strength validation
   - Email format validation
   - Confirm password matching

3. **User Profile Component** (`src/app/views/user-profile/`)
   - Display user information
   - Show assigned permissions
   - Refresh profile data
   - Logout action

4. **403 Forbidden Page** (`src/app/views/pages/page403/`)
   - Displayed when user lacks required permissions
   - Navigation options to dashboard or profile

## Data Models

### User Interface
```typescript
interface User {
  id: number;
  username: string;
  email: string;
  role_id: number;
  role?: string;
  is_active: boolean;
  last_login: string | null;
  permissions?: Permission[];
}
```

### Permission Interface
```typescript
interface Permission {
  resource: string;
  action: string;
}
```

### User Roles
- **Viewer (role_id: 1)**: Read-only access to data
- **Trader (role_id: 2)**: Can execute trades and view data
- **Admin (role_id: 3)**: Full system access

## Backend API Endpoints

All endpoints are prefixed with `http://localhost:8000/api/auth/`

### POST /login
**Request:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "jwt-token-here",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user": {
      "id": 1,
      "username": "testuser",
      "email": "test@example.com",
      "role_id": 2,
      "is_active": true,
      "last_login": "2024-01-01T00:00:00Z",
      "permissions": [
        { "resource": "trading", "action": "execute" },
        { "resource": "positions", "action": "read" }
      ]
    }
  }
}
```

### POST /register
**Request:**
```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "role_id": 1
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user": { /* User object */ }
  }
}
```

### GET /me
Requires authentication (Bearer token in Authorization header)

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "testuser",
    "email": "test@example.com",
    "role_id": 2,
    "is_active": true,
    "last_login": "2024-01-01T00:00:00Z",
    "permissions": [...]
  }
}
```

## Route Configuration

### Public Routes (No Authentication)
- `/login` - Login page
- `/register` - Registration page
- `/404` - Not found page
- `/500` - Server error page

### Protected Routes (Authentication Required)
All routes under the default layout require authentication:
- `/dashboard` - Dashboard (no specific permission)
- `/profile` - User profile (no specific permission)
- `/positions` - Positions (requires `positions:read`)
- `/paper-trading` - Paper trading (requires `trading:execute`)
- `/settings` - Settings (requires `settings:write`)
- `/markets` - Market data (no specific permission)
- `/signals` - Trading signals (no specific permission)
- `/backtest` - Backtesting (no specific permission)
- `/strategy` - Strategy configuration (no specific permission)
- `/models` - AI models (no specific permission)
- `/news` - News feed (no specific permission)
- `/trade-journal` - Trade journal (no specific permission)
- `/system-logs` - System logs (no specific permission)

### Error Routes
- `/403` - Forbidden (insufficient permissions)

## Usage Examples

### Protecting a Route with Authentication
```typescript
{
  path: 'dashboard',
  loadChildren: () => import('./views/dashboard/routes').then(m => m.routes),
  canActivate: [authGuard]
}
```

### Protecting a Route with Specific Permission
```typescript
{
  path: 'trading',
  loadChildren: () => import('./views/trading/routes').then(m => m.routes),
  canActivate: [permissionGuard],
  data: { resource: 'trading', action: 'execute' }
}
```

### Checking Permissions in a Component
```typescript
import { Component, inject } from '@angular/core';
import { AuthService } from './core/services/auth.service';

@Component({...})
export class MyComponent {
  private authService = inject(AuthService);

  canExecuteTrades(): boolean {
    return this.authService.hasPermission('trading', 'execute');
  }

  canViewSettings(): boolean {
    return this.authService.hasPermission('settings', 'read');
  }
}
```

### Conditional Template Rendering
```html
@if (authService.hasPermission('trading', 'execute')) {
  <button (click)="executeTrade()">Execute Trade</button>
}

@if (authService.isAuthenticated()) {
  <div>Welcome, {{ authService.currentUser()?.username }}!</div>
}
```

### Manual Login/Logout
```typescript
// Login
this.authService.login('username', 'password').subscribe({
  next: (response) => {
    console.log('Login successful', response);
    this.router.navigate(['/dashboard']);
  },
  error: (error) => {
    console.error('Login failed', error);
  }
});

// Logout
this.authService.logout(); // Automatically redirects to /login
```

## State Management

The auth system uses Angular Signals for reactive state management:

```typescript
// Reactive signals
readonly isAuthenticated = computed(() => this.authState().isAuthenticated);
readonly currentUser = computed(() => this.authState().currentUser);
readonly token = computed(() => this.authState().token);
```

State is automatically persisted to localStorage:
- `mantis_auth_token`: JWT token
- `mantis_current_user`: User object (JSON)

## Security Features

1. **JWT Token Storage**: Tokens stored in localStorage with automatic loading on app init
2. **Auto-logout on 401**: Interceptor automatically logs out on authentication failures
3. **Permission Checking**: Fine-grained permission checks at route and component level
4. **Password Validation**: Minimum 6 characters, requires uppercase, lowercase, and numbers
5. **Form Validation**: Real-time validation feedback with Italian error messages
6. **CSRF Protection**: Backend should implement CSRF tokens (not handled by frontend)

## Styling

The auth pages use MANTIS AI branding:
- **Primary Color**: `#00d97e` (mantis green)
- **Accent Color**: `#39FF14` (neon green)
- **Dark Background**: `#0d1117`
- **Surface Color**: `#161b22`

Custom CSS classes:
- `.mantis-brand-text` - Neon green text with glow effect
- `.mantis-btn-primary` - Primary action button (green background)
- `.mantis-btn-secondary` - Secondary action button (green border)
- `.mantis-card-gradient` - Card with gradient background

## Testing

Test files included:
- `auth.service.spec.ts` - AuthService unit tests
- `auth.guard.spec.ts` - Auth guard tests
- `login.component.spec.ts` - Login component tests

Run tests:
```bash
cd frontend
npm test
```

## Troubleshooting

### User logged out unexpectedly
- Check if token expired (default: 3600 seconds / 1 hour)
- Check browser console for 401 errors
- Verify backend is running on http://localhost:8000

### Permission denied (403)
- Check user's role and permissions in `/profile`
- Verify route data configuration matches backend permissions
- Check browser console for permission requirements

### Login not working
- Verify backend API is running
- Check Network tab for API response
- Verify credentials are correct
- Check CORS configuration on backend

### State not persisting
- Check browser localStorage for `mantis_auth_token` and `mantis_current_user`
- Verify localStorage is not disabled in browser
- Clear localStorage and try logging in again

## Future Enhancements

Potential improvements:
1. Token refresh mechanism (auto-refresh before expiry)
2. Remember me with longer-lived tokens
3. OAuth2/SSO integration (Google, GitHub)
4. Two-factor authentication (2FA)
5. Password reset flow via email
6. User profile editing
7. Session management (view/revoke active sessions)
8. Permission hierarchy/inheritance
9. Rate limiting on login attempts
10. Audit logging of authentication events

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) - Project overview
- [05-FRONTEND-GUIDE.md](../docs/05-FRONTEND-GUIDE.md) - Frontend architecture
- [01-ARCHITECTURE.md](../docs/01-ARCHITECTURE.md) - System architecture
