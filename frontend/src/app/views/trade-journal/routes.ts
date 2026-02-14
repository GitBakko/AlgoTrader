import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./trade-journal.component').then(m => m.TradeJournalComponent),
    data: { title: 'Trade Journal' }
  }
];
