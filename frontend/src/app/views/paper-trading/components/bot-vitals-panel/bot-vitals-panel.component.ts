import { ChangeDetectionStrategy, Component, computed, effect, input, signal } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import type { BotVitals } from '../../../../core/models/paper-trading';

/**
 * Bot Vitals Panel — left rail (HANDOFF §3.2).
 *
 * Sections (top → bottom):
 *  1. Header  · pulsing dot + BOT VITALS label (CHIP-01)
 *  2. ECG     · static reference trace + a one-shot beat overlay that
 *               fires every time the parent's `heartbeat` input changes
 *               (i.e. every time fresh data arrives).
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
  /** Bumped by the parent every time a relevant data signal changes. The
   *  panel beats the ECG once per bump — never on a CSS infinite loop. */
  readonly heartbeat = input<string | number>(0);

  readonly stateLabel = computed(() => this.vitals().state);

  readonly intervalLabel = computed(() => {
    const sec = this.vitals().intervalSec;
    if (!sec || sec <= 0) return '—';
    if (sec >= 60) return `${Math.floor(sec / 60)}m`;
    return `${sec}s`;
  });

  readonly tickLabel = computed(() => {
    const t = this.vitals().lastTickAgo;
    if (t === null || t === undefined || !Number.isFinite(t) || t <= 0) {
      return '—';
    }
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

  /** True for the duration of a single heartbeat animation. The beat
   *  attaches the `is-beating` class on the ECG element which kicks off
   *  a one-shot `stroke-dashoffset` draw. */
  readonly beating = signal(false);

  constructor() {
    effect(() => {
      // Read the heartbeat input so this effect re-runs on every nonce
      // change. Reset to false then schedule a fresh true on the next
      // animation frame so the CSS animation actually restarts.
      this.heartbeat();
      this.beating.set(false);
      // requestAnimationFrame is microtask-safe in Angular zoneless / OnPush.
      const raf = typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame
        : (cb: FrameRequestCallback) => setTimeout(() => cb(0), 16);
      raf(() => this.beating.set(true));
    });
  }

  onBeatEnd(event: AnimationEvent): void {
    if ((event.animationName ?? '').includes('pv-bv-beat')) {
      this.beating.set(false);
    }
  }
}
