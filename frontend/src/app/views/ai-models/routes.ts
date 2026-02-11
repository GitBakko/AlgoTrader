import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./ai-models.component').then(m => m.AiModelsComponent),
    data: { title: 'AI Models' }
  }
];
