import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./positions.component').then(m => m.PositionsComponent),
    data: { title: 'Positions' }
  }
];
