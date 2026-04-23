import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import {
  ButtonDirective,
  CardBodyComponent,
  CardComponent,
  CardHeaderComponent,
  ColComponent,
  FormDirective,
  RowComponent,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';

interface Token {
  readonly name: string;
  readonly cssVar: string;
  readonly description?: string;
}

@Component({
  selector: 'app-design-system',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './design-system.component.html',
  styleUrls: ['./design-system.component.scss'],
  imports: [
    CardComponent,
    CardHeaderComponent,
    CardBodyComponent,
    RowComponent,
    ColComponent,
    ButtonDirective,
    IconDirective,
    FormDirective,
  ],
})
export class DesignSystemComponent {
  private readonly doc = inject(DOCUMENT);

  readonly brandColors: readonly Token[] = [
    { name: 'Neon', cssVar: '--mantis-neon', description: 'Hero accent · dark only · profit' },
    { name: 'Green', cssVar: '--mantis-green', description: 'Primary brand · WCAG-friendlier' },
    { name: 'Cyan', cssVar: '--mantis-cyan', description: 'Secondary · predicted / info' },
    { name: 'Profit', cssVar: '--mantis-profit' },
    { name: 'Loss', cssVar: '--mantis-loss' },
    { name: 'Warning', cssVar: '--mantis-warning' },
    { name: 'Neutral', cssVar: '--mantis-neutral' },
  ];

  readonly surfaces: readonly Token[] = [
    { name: 'surface-0', cssVar: '--mantis-surface-0', description: 'void / deepest' },
    { name: 'surface-1', cssVar: '--mantis-surface-1', description: 'body bg' },
    { name: 'surface-2', cssVar: '--mantis-surface-2', description: 'cards · sidebar' },
    { name: 'surface-3', cssVar: '--mantis-surface-3', description: 'dropdowns' },
    { name: 'surface-4', cssVar: '--mantis-surface-4', description: 'modals · toasts' },
    { name: 'surface-5', cssVar: '--mantis-surface-5', description: 'tooltips' },
  ];

  readonly typeScale: readonly Token[] = [
    { name: 'xxs · 9px',   cssVar: '--mantis-fs-xxs' },
    { name: 'xs · 10px',   cssVar: '--mantis-fs-xs' },
    { name: 'sm · 11px',   cssVar: '--mantis-fs-sm' },
    { name: 'md · 12px',   cssVar: '--mantis-fs-md' },
    { name: 'base · 13px', cssVar: '--mantis-fs-base' },
    { name: 'body · 14px', cssVar: '--mantis-fs-body' },
    { name: 'lg · 16px',   cssVar: '--mantis-fs-lg' },
    { name: 'xl · 18px',   cssVar: '--mantis-fs-xl' },
    { name: '2xl · 20px',  cssVar: '--mantis-fs-2xl' },
    { name: '3xl · 24px',  cssVar: '--mantis-fs-3xl' },
    { name: '4xl · 32px',  cssVar: '--mantis-fs-4xl' },
  ];

  readonly spacingScale: readonly { name: string; value: string }[] = [
    { name: 'space-1', value: '4px' },
    { name: 'space-2', value: '8px' },
    { name: 'space-3', value: '12px' },
    { name: 'space-4', value: '16px' },
    { name: 'space-6', value: '24px' },
    { name: 'space-8', value: '32px' },
    { name: 'space-12', value: '48px' },
  ];

  readonly radii: readonly { name: string; value: string; usage: string }[] = [
    { name: 'sm',   value: '4px',   usage: 'badges · status pills · form controls' },
    { name: 'md',   value: '8px',   usage: 'cards · buttons' },
    { name: 'lg',   value: '12px',  usage: 'reserved' },
    { name: 'xl',   value: '24px',  usage: 'auth glass containers' },
    { name: 'pill', value: '100px', usage: 'P&L pills · WS status pills' },
  ];

  readonly shadows: readonly { name: string; description: string }[] = [
    { name: 'shadow-sm',  description: '0 1px 3px · in-grid cards' },
    { name: 'shadow-md',  description: '0 4px 12px · dropdowns' },
    { name: 'shadow-lg',  description: '0 8px 24px · modals' },
    { name: 'glow-green', description: '0 0 8px · subtle brand glow' },
    { name: 'glow-neon',  description: '0 0 12px · hero glow (dark only)' },
  ];

  // Resolved value display — reads live from computed style on :root.
  readonly resolvedValues = computed(() => {
    const style = this.doc.defaultView?.getComputedStyle(this.doc.documentElement);
    if (!style) return {};
    const all = [
      ...this.brandColors,
      ...this.surfaces,
      ...this.typeScale,
    ];
    return all.reduce<Record<string, string>>((acc, t) => {
      acc[t.cssVar] = style.getPropertyValue(t.cssVar).trim();
      return acc;
    }, {});
  });

  readonly signalStatuses = [
    { cls: 'executed',     label: 'EXECUTED' },
    { cls: 'rejected',     label: 'REJECTED' },
    { cls: 'predicted',    label: 'PREDICTED' },
    { cls: 'hold',         label: 'HOLD' },
    { cls: 'market_closed', label: 'MARKET CLOSED' },
  ] as const;

  readonly regimes = [
    { cls: 'trending_up',   label: 'Trending ↑' },
    { cls: 'trending_down', label: 'Trending ↓' },
    { cls: 'ranging',       label: 'Ranging' },
  ] as const;

  readonly tradingModes = [
    { cls: 'demo',  label: 'DEMO' },
    { cls: 'live',  label: 'LIVE' },
    { cls: 'paper', label: 'PAPER' },
  ] as const;

  // Interactive pulse toggle, for showing reduced-motion compliance.
  readonly pulseActive = signal(true);

  togglePulse(): void {
    this.pulseActive.set(!this.pulseActive());
  }
}
