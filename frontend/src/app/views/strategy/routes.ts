import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./strategy.component').then(m => m.StrategyComponent),
    data: { title: 'Strategy' }
  }
];
