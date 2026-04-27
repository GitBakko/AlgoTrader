import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Skeleton placeholder for a single KPI cell (KPI Pattern §2.1).
 * Renders a pulsing card with a label, value, and optional sparkline rect so
 * the layout doesn't shift when data resolves.
 */
@Component({
  selector: 'app-skeleton-kpi-cell',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="kpi-skel"
         [attr.data-accent]="accent()"
         role="status"
         aria-label="Caricamento KPI">
      <span class="kpi-skel__label"></span>
      <span class="kpi-skel__value"></span>
      @if (showSpark()) {
        <span class="kpi-skel__spark"></span>
      }
    </div>
  `,
  styles: [`
    :host { display: block; height: 100%; }

    .kpi-skel {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 12px 14px;
      background: var(--mantis-surface-2, #161b22);
      border: 1px solid rgba(0, 217, 126, .15);
      border-top: 2px solid rgba(0, 217, 126, .35);
      border-radius: var(--mantis-radius-md, 6px);
      min-height: 84px;
      overflow: hidden;

      &[data-accent="profit"] { border-top-color: rgba(57, 255, 20, .55); }
      &[data-accent="loss"]   { border-top-color: rgba(255, 61, 87, .55); }
      &[data-accent="info"]   { border-top-color: rgba(0, 229, 255, .55); }
      &[data-accent="warn"]   { border-top-color: rgba(255, 176, 32, .55); }
    }

    .kpi-skel__label,
    .kpi-skel__value,
    .kpi-skel__spark {
      display: block;
      border-radius: var(--mantis-radius-sm, 4px);
      background: linear-gradient(
        90deg,
        rgba(255, 255, 255, .04) 0%,
        rgba(255, 255, 255, .12) 50%,
        rgba(255, 255, 255, .04) 100%
      );
      background-size: 200% 100%;
      animation: kpi-shimmer 1.4s ease-in-out infinite;
    }

    .kpi-skel__label {
      width: 45%;
      height: 8px;
    }

    .kpi-skel__value {
      width: 70%;
      height: 22px;
    }

    .kpi-skel__spark {
      position: absolute;
      top: 12px;
      right: 12px;
      width: 56px;
      height: 24px;
      opacity: .65;
    }

    @keyframes kpi-shimmer {
      0%   { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
  `],
})
export class SkeletonKpiCellComponent {
  readonly showSpark = input<boolean>(false);
  /** Accent variant — drives the border-top color to match the resolved KPI. */
  readonly accent = input<'profit' | 'loss' | 'info' | 'warn' | 'neutral'>('neutral');
}
