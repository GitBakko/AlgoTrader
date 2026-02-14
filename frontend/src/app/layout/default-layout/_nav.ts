import { INavData } from '@coreui/angular';

export const navItems: INavData[] = [
  {
    name: 'Dashboard',
    url: '/dashboard',
    iconComponent: { name: 'cil-speedometer' }
  },
  {
    title: true,
    name: 'Trading'
  },
  {
    name: 'Posizioni',
    url: '/positions',
    iconComponent: { name: 'cil-layers' }
  },
  {
    name: 'Segnali',
    url: '/signals',
    iconComponent: { name: 'cil-bolt' }
  },
  {
    name: 'Mercati',
    url: '/markets',
    iconComponent: { name: 'cil-chart-line' }
  },
  {
    name: 'News Feed',
    url: '/news',
    iconComponent: { name: 'cil-newspaper' }
  },
  {
    name: 'Paper Trading',
    url: '/paper-trading',
    iconComponent: { name: 'cil-media-play' }
  },
  {
    name: 'Trade Journal',
    url: '/trade-journal',
    iconComponent: { name: 'cil-book' }
  },
  {
    title: true,
    name: 'Analisi'
  },
  {
    name: 'Backtest',
    url: '/backtest',
    iconComponent: { name: 'cil-history' }
  },
  {
    name: 'Strategia',
    url: '/strategy',
    iconComponent: { name: 'cil-settings' }
  },
  {
    name: 'Modelli AI',
    url: '/models',
    iconComponent: { name: 'cil-brain' }
  },
  {
    title: true,
    name: 'Sistema',
    class: 'mt-auto'
  },
  {
    name: 'Impostazioni',
    url: '/settings',
    iconComponent: { name: 'cil-applications-settings' }
  },
  {
    name: 'System Logs',
    url: '/system-logs',
    iconComponent: { name: 'cil-clipboard' }
  }
];
