import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { PositionCardComponent } from '../position-card/position-card.component';
import type { PaperTradingPosition } from '../../../../core/models/paper-trading';

/**
 * Active Positions Cockpit — center hero (HANDOFF §3.6).
 *
 * Header (`POSIZIONI APERTE` + count + total P&L) over a vertical stack
 * of `position-card`. Empty state when there are no live positions.
 */
@Component({
  selector: 'app-active-positions-cockpit',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DecimalPipe, PositionCardComponent],
  templateUrl: './active-positions-cockpit.component.html',
  styleUrls: ['./active-positions-cockpit.component.scss'],
})
export class ActivePositionsCockpitComponent {
  readonly positions = input.required<PaperTradingPosition[]>();
  readonly signalsTotal = input<number>(0);
  readonly currency = input<string>('USD');

  readonly closeRequested = output<PaperTradingPosition>();
  readonly detailsRequested = output<PaperTradingPosition>();

  readonly totalPnl = computed(() =>
    this.positions().reduce((sum, p) => sum + p.pnlEur, 0),
  );

  readonly currencySym = computed(() => {
    const code = (this.currency() ?? 'USD').replace(/d$/, '');
    switch (code) {
      case 'USD': return '$';
      case 'EUR': return '€';
      case 'GBP': return '£';
      default:    return code + ' ';
    }
  });

  onClose(p: PaperTradingPosition): void {
    this.closeRequested.emit(p);
  }

  onDetails(p: PaperTradingPosition): void {
    this.detailsRequested.emit(p);
  }
}
