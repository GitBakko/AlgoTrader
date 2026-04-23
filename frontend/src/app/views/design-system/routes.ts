import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./design-system.component').then((m) => m.DesignSystemComponent),
    data: { title: 'Design System' },
  },
];
