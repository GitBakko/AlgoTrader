import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full'
  },
  {
    path: '',
    loadComponent: () => import('./layout').then(m => m.DefaultLayoutComponent),
    data: { title: 'Home' },
    children: [
      {
        path: 'dashboard',
        loadChildren: () => import('./views/dashboard/routes').then(m => m.routes)
      },
      {
        path: 'positions',
        loadChildren: () => import('./views/positions/routes').then(m => m.routes)
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
        loadChildren: () => import('./views/settings/routes').then(m => m.routes)
      }
    ]
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
