import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./dashboard-v2.component').then(m => m.DashboardV2Component),
    data: {
      title: 'Dashboard v2',
    },
  },
];
