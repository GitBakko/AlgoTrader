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
    name: 'Positions',
    url: '/positions',
    iconComponent: { name: 'cil-layers' }
  },
  {
    name: 'Signals',
    url: '/signals',
    iconComponent: { name: 'cil-bolt' }
  },
  {
    name: 'Markets',
    url: '/markets',
    iconComponent: { name: 'cil-chart-line' }
  },
  {
    name: 'Paper Trading',
    url: '/paper-trading',
    iconComponent: { name: 'cil-media-play' }
  },
  {
    title: true,
    name: 'Analysis'
  },
  {
    name: 'Backtest',
    url: '/backtest',
    iconComponent: { name: 'cil-history' }
  },
  {
    name: 'Strategy',
    url: '/strategy',
    iconComponent: { name: 'cil-settings' }
  },
  {
    name: 'AI Models',
    url: '/models',
    iconComponent: { name: 'cil-brain' }
  },
  {
    title: true,
    name: 'System',
    class: 'mt-auto'
  },
  {
    name: 'Settings',
    url: '/settings',
    iconComponent: { name: 'cil-applications-settings' }
  }
];
