import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';

export type CockpitState = 'RUNNING' | 'IDLE' | 'ERROR';
export type CockpitMode = 'DEMO' | 'LIVE' | 'PAPER';
export type CockpitMarketStatus = 'OPEN' | 'CLOSED' | 'PRE';

/**
 * HDR-01 — Cockpit Header (Style Bible §1.2)
 * Live cockpit pages (Dashboard, Paper Trading) with critical actions.
 * - Logo signet + page title
 * - Status pills (RUNNING / DEMO / market)
 * - STOP (warning) + EMERGENCY (danger) on the right
 */
@Component({
  selector: 'app-cockpit-header',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule],
  templateUrl: './cockpit-header.component.html',
  styleUrls: ['./cockpit-header.component.scss'],
  host: {
    'class': 'cockpit-header',
    '[attr.data-state]': 'state()',
  },
})
export class CockpitHeaderComponent {
  readonly pageTitle = input.required<string>();
  readonly state = input<CockpitState>('IDLE');
  readonly mode = input<CockpitMode>('DEMO');
  readonly marketStatus = input<CockpitMarketStatus | null>(null);
  readonly lastTickAgo = input<number | null>(null);
  readonly stopBusy = input<boolean>(false);
  readonly emergencyBusy = input<boolean>(false);

  readonly stopClicked = output<void>();
  readonly emergencyClicked = output<void>();

  readonly stateLabel = computed<string>(() => {
    switch (this.state()) {
      case 'RUNNING': return 'RUNNING';
      case 'ERROR':   return 'ERROR';
      default:        return 'IDLE';
    }
  });

  readonly isRunning = computed<boolean>(() => this.state() === 'RUNNING');

  readonly toggleLabel = computed<string>(() => (this.isRunning() ? 'STOP' : 'START'));

  readonly toggleAriaLabel = computed<string>(() =>
    this.isRunning() ? 'Stop paper trading loop' : 'Start paper trading loop'
  );

  readonly tickLabel = computed<string | null>(() => {
    const t = this.lastTickAgo();
    if (t === null || t === undefined) return null;
    if (t < 60) return `${t.toFixed(1)}s`;
    const m = Math.floor(t / 60);
    return `${m}m ${Math.floor(t % 60)}s`;
  });

  onStop(): void {
    if (this.stopBusy()) return;
    this.stopClicked.emit();
  }

  onEmergency(): void {
    if (this.emergencyBusy()) return;
    this.emergencyClicked.emit();
  }
}
