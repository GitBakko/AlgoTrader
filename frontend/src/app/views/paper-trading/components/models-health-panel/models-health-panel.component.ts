import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import type { ModelsHealth } from '../../../../core/models/paper-trading';

/**
 * Models Health Panel — left rail (HANDOFF §3.4).
 *
 * Header MODELS + loaded/total badge.
 * Bullet grid (per-asset dots: green=ok, red=missing, amber=stale).
 */
@Component({
  selector: 'app-models-health-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule],
  templateUrl: './models-health-panel.component.html',
  styleUrls: ['./models-health-panel.component.scss'],
})
export class ModelsHealthPanelComponent {
  readonly health = input.required<ModelsHealth>();

  readonly badgeClass = computed(() => {
    const h = this.health();
    if (h.loaded === h.total && h.total > 0) return 'is-ok';
    if (h.loaded === 0) return 'is-missing';
    return 'is-partial';
  });
}
