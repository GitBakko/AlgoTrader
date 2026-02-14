import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./system-logs.component').then(m => m.SystemLogsComponent),
    data: {
      title: 'System Logs'
    }
  }
];
