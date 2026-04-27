import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import type { BotVitals } from '../../../../core/models/paper-trading';

/**
 * Bot Vitals Panel — left rail (HANDOFF §3.2).
 *
 * Sections (top → bottom):
 *  1. Header  · pulsing dot + BOT VITALS label (CHIP-01)
 *  2. ECG     · static SVG polyline with last-tick overlay
 *  3. Stats   · 2x2 grid (ITER · INTERVAL · UPTIME · ERRORS)
 *  4. Signals · donut + total/executed counts + conv %
 */
@Component({
  selector: 'app-bot-vitals-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DecimalPipe],
  templateUrl: './bot-vitals-panel.component.html',
  styleUrls: ['./bot-vitals-panel.component.scss'],
})
export class BotVitalsPanelComponent {
  readonly vitals = input.required<BotVitals>();

  readonly stateLabel = computed(() => this.vitals().state);

  readonly intervalLabel = computed(() => {
    const sec = this.vitals().intervalSec;
    if (sec >= 60) return `${Math.floor(sec / 60)}m`;
    return `${sec}s`;
  });

  readonly tickLabel = computed(() => {
    const t = this.vitals().lastTickAgo;
    if (t < 60) return `${t.toFixed(1)}s`;
    return `${Math.floor(t / 60)}m ${Math.floor(t % 60)}s`;
  });

  // Donut math — slice arc lengths on a circumference of 100.
  readonly donut = computed(() => {
    const s = this.vitals().signals;
    const total = Math.max(1, s.total);
    const exec = (s.executed / total) * 100;
    const rej = (s.rejected / total) * 100;
    const hold = (s.hold / total) * 100;
    return {
      exec,
      rej,
      hold,
      execOffset: 0,
      rejOffset: -exec,
      holdOffset: -(exec + rej),
    };
  });

  readonly conversionPct = computed(() => this.vitals().signals.conversion * 100);
}
