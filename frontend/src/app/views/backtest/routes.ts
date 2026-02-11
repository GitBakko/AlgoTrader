import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./backtest.component').then(m => m.BacktestComponent),
    data: { title: 'Backtest' }
  }
];
