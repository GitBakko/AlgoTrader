import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * Skeleton placeholder mirroring the layout of `position-card` (HANDOFF §3.6)
 * — header row, sl/entry/tp triplet, P&L block, meta — so the cockpit
 * doesn't shift when broker positions resolve.
 */
@Component({
  selector: 'app-skeleton-position-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="pos-skel" role="status" aria-label="Caricamento posizione">
      <header class="pos-skel__head">
        <span class="pos-skel__avatar"></span>
        <span class="pos-skel__chip pos-skel__chip--lg"></span>
        <span class="pos-skel__chip pos-skel__chip--md"></span>
        <span class="pos-skel__spacer"></span>
        <span class="pos-skel__chip pos-skel__chip--md"></span>
      </header>

      <div class="pos-skel__triplet">
        <span class="pos-skel__triplet-cell"></span>
        <span class="pos-skel__triplet-cell"></span>
        <span class="pos-skel__triplet-cell"></span>
      </div>

      <section class="pos-skel__pnl">
        <span class="pos-skel__line pos-skel__line--xl"></span>
        <span class="pos-skel__line pos-skel__line--sm"></span>
      </section>

      <footer class="pos-skel__foot">
        <span class="pos-skel__chip pos-skel__chip--sm"></span>
        <span class="pos-skel__chip pos-skel__chip--sm"></span>
        <span class="pos-skel__chip pos-skel__chip--sm"></span>
      </footer>
    </article>
  `,
  styles: [`
    :host { display: block; }

    .pos-skel {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 14px;
      background: var(--mantis-surface-2, #161b22);
      border: 1px solid rgba(0, 217, 126, .12);
      border-left: 3px solid rgba(0, 217, 126, .35);
      border-radius: var(--mantis-radius-md, 6px);
    }

    .pos-skel__head,
    .pos-skel__foot {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .pos-skel__spacer { flex: 1 1 auto; }

    .pos-skel__avatar {
      width: 22px;
      height: 22px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .pos-skel__chip,
    .pos-skel__triplet-cell,
    .pos-skel__avatar,
    .pos-skel__line {
      background: linear-gradient(
        90deg,
        rgba(255, 255, 255, .04) 0%,
        rgba(255, 255, 255, .12) 50%,
        rgba(255, 255, 255, .04) 100%
      );
      background-size: 200% 100%;
      animation: pos-skel-shimmer 1.4s ease-in-out infinite;
      border-radius: var(--mantis-radius-sm, 4px);
    }

    .pos-skel__chip { height: 14px; }
    .pos-skel__chip--sm { width: 56px; }
    .pos-skel__chip--md { width: 88px; }
    .pos-skel__chip--lg { width: 120px; }

    .pos-skel__triplet {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }

    .pos-skel__triplet-cell {
      height: 56px;
      border-radius: var(--mantis-radius-sm, 4px);
    }

    .pos-skel__pnl {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .pos-skel__line { display: block; border-radius: var(--mantis-radius-sm, 4px); }
    .pos-skel__line--xl { width: 65%; height: 28px; }
    .pos-skel__line--sm { width: 30%; height: 10px; }

    @keyframes pos-skel-shimmer {
      0%   { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
  `],
})
export class SkeletonPositionCardComponent {}
