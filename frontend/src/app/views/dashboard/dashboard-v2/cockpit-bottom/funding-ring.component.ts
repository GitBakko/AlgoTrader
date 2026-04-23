import { Component, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Funding exposure ring — BTC / ETH perpetual funding rate.
 *
 * TODO — BACKEND (next sprint, MANDATORY, see sprint plan §2.2):
 *   GET /api/funding/current?epic=BTCUSD
 *   → { rate_8h, next_funding_utc, notional_eur, side, accumulated_7d }
 *
 * Until the endpoint exists this component renders a dimmed ring with
 * a TODO banner — no fabricated rates.
 */
@Component({
  selector: 'app-funding-ring',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './funding-ring.component.html',
  styleUrl: './funding-ring.component.scss',
})
export class FundingRingComponent {
  // Placeholder static viewbox metrics — rendered but unwired.
  readonly ringCircumference = 238.76; // 2 * π * 38
}
