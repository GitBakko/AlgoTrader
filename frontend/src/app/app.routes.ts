import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { permissionGuard } from './core/guards/permission.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full'
  },
  // Public routes (no authentication required)
  {
    path: 'login',
    loadComponent: () => import('./views/pages/login/login.component').then(m => m.LoginComponent),
    data: { title: 'Login' }
  },
  {
    path: 'register',
    loadComponent: () => import('./views/pages/register/register.component').then(m => m.RegisterComponent),
    data: { title: 'Register' }
  },
  // Protected routes (authentication required)
  {
    path: '',
    loadComponent: () => import('./layout').then(m => m.DefaultLayoutComponent),
    canActivate: [authGuard],
    data: { title: 'Home' },
    children: [
      {
        path: 'dashboard',
        loadChildren: () => import('./views/dashboard/routes').then(m => m.routes)
      },
      {
        path: 'profile',
        loadChildren: () => import('./views/user-profile/routes').then(m => m.routes)
      },
      {
        path: 'positions',
        loadChildren: () => import('./views/positions/routes').then(m => m.routes),
        canActivate: [permissionGuard],
        data: { resource: 'positions', action: 'read' }
      },
      {
        path: 'signals',
        loadChildren: () => import('./views/signals/routes').then(m => m.routes)
      },
      {
        path: 'markets',
        loadChildren: () => import('./views/markets/routes').then(m => m.routes)
      },
      {
        path: 'news',
        loadChildren: () => import('./views/news/news.routes').then(m => m.routes)
      },
      {
        path: 'paper-trading',
        loadChildren: () => import('./views/paper-trading/routes').then(m => m.routes),
        canActivate: [permissionGuard],
        data: { resource: 'trading', action: 'execute' }
      },
      {
        path: 'trade-journal',
        loadChildren: () => import('./views/trade-journal/routes').then(m => m.routes)
      },
      {
        path: 'backtest',
        loadChildren: () => import('./views/backtest/routes').then(m => m.routes)
      },
      {
        path: 'strategy',
        loadChildren: () => import('./views/strategy/routes').then(m => m.routes)
      },
      {
        path: 'models',
        loadChildren: () => import('./views/ai-models/routes').then(m => m.routes)
      },
      {
        path: 'settings',
        loadChildren: () => import('./views/settings/routes').then(m => m.routes),
        canActivate: [permissionGuard],
        data: { resource: 'settings', action: 'write' }
      },
      {
        path: 'system-logs',
        loadChildren: () => import('./views/system-logs/routes').then(m => m.routes)
      }
    ]
  },
  // Error pages
  {
    path: '403',
    loadComponent: () => import('./views/pages/page403/page403.component').then(m => m.Page403Component),
    data: { title: 'Page 403' }
  },
  {
    path: '404',
    loadComponent: () => import('./views/pages/page404/page404.component').then(m => m.Page404Component),
    data: { title: 'Page 404' }
  },
  {
    path: '500',
    loadComponent: () => import('./views/pages/page500/page500.component').then(m => m.Page500Component),
    data: { title: 'Page 500' }
  },
  { path: '**', redirectTo: '404' }
];
