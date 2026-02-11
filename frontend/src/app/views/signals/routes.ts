import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./signals.component').then(m => m.SignalsComponent),
    data: { title: 'Signals' }
  }
];
