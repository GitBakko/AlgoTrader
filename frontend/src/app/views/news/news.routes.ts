import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./news.component').then(m => m.NewsComponent),
    data: { title: 'News Feed' }
  }
];
