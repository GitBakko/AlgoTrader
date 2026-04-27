import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./paper-trading.component').then(m => m.PaperTradingComponent),
    data: { title: 'Paper Trading', screenLabel: '02 Paper Trading' }
  }
];
