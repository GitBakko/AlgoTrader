import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./notifications.component').then(m => m.NotificationsComponent),
    data: { title: 'Notifiche' }
  }
];
