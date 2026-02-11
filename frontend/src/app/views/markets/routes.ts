import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./markets.component').then(m => m.MarketsComponent),
    data: { title: 'Markets' }
  }
];
