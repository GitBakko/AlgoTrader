import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { EpicLogoComponent } from '../../../../shared/components/epic-logo/epic-logo.component';
import { PriceFormatPipe } from '../../../../shared/pipes/price-format.pipe';
import type { PaperTradingPosition } from '../../../../core/models/paper-trading';

/**
 * Position Card — center hero (HANDOFF §3.6).
 *
 * CARD-03 with state border-left (profit/loss). Four-column grid:
 *   1. Asset · direction · size · age · trailing
 *   2. SL ←→ Entry ←→ TP visualization + numeric triplet
 *   3. P&L hero (value + % + price chart since open, side-by-side)
 *   4. Meta (R:R · → SL · → TP) + Close button
 */
@Component({
  selector: 'app-position-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DecimalPipe, EpicLogoComponent, PriceFormatPipe],
  templateUrl: './position-card.component.html',
  styleUrls: ['./position-card.component.scss'],
})
export class PositionCardComponent {
  readonly position = input.required<PaperTradingPosition>();
  readonly currency = input<string>('USD');
  /** Live account equity (broker). When 0/undefined, exposure % renders as
   *  a dash and only the notional is shown. */
  readonly equity = input<number>(0);

  readonly closeClicked = output<PaperTradingPosition>();
  readonly detailsClicked = output<PaperTradingPosition>();

  /** Raw notional value of the position in account currency (size × current). */
  readonly notional = computed(() => {
    const p = this.position();
    return Math.abs(p.size * p.current);
  });

  /** Exposure as percent of live account equity. Null when equity unknown. */
  readonly exposurePct = computed<number | null>(() => {
    const eq = this.equity();
    if (!eq || !Number.isFinite(eq)) return null;
    return (this.notional() / eq) * 100;
  });

  readonly currencySym = computed(() => {
    const code = (this.currency() ?? 'USD').replace(/d$/, '');
    switch (code) {
      case 'USD': return '$';
      case 'EUR': return '€';
      case 'GBP': return '£';
      default:    return code + ' ';
    }
  });

  readonly inProfit = computed(() => this.position().pnlEur >= 0);

  readonly distToSlPct = computed(() => {
    const p = this.position();
    if (!p.current) return 0;
    return Math.abs(((p.stopLoss - p.current) / p.current) * 100);
  });

  readonly distToTpPct = computed(() => {
    const p = this.position();
    if (!p.current) return 0;
    return Math.abs(((p.takeProfit - p.current) / p.current) * 100);
  });

  readonly ageLabel = computed(() => formatAge(this.position().ageSec));

  /** Trailing-stop phase badge: short label + tone + tooltip explaining why
   *  the position is in this state. Returns null when phase is INITIAL or
   *  the manager is not tracking the position (no badge rendered). */
  readonly phaseBadge = computed<{
    label: string;
    tone: 'neutral' | 'profit' | 'lock' | 'trail';
    tooltip: string;
  } | null>(() => {
    const p = this.position();
    const phase = p.trailingPhase;
    if (!phase || phase === 'INITIAL') return null;
    if (phase === 'BREAKEVEN') {
      return {
        label: 'BE',
        tone: 'profit',
        tooltip:
          `Break-even attivato — prezzo ha raggiunto TP1 ` +
          `(midpoint strategy TP), 50% chiuso e SL spostato a entry ` +
          `${p.entry.toFixed(4)}. Da qui non perdi più capitale ` +
          `sulla restante metà.`,
      };
    }
    if (phase === 'TP1_LOCK') {
      return {
        label: 'TP1 LOCK',
        tone: 'lock',
        tooltip:
          `Profitto bloccato a TP1 — prezzo ha raggiunto TP2, ` +
          `SL alzato al livello di TP1. Anche col retrace il P&L ` +
          `chiude positivo.`,
      };
    }
    if (phase === 'TRAILING') {
      return {
        label: 'TRAIL',
        tone: 'trail',
        tooltip:
          `Trailing ATR-anchored attivo — SL ratchetta dietro il prezzo ` +
          `con multiplier ATR ` +
          `${p.direction === 'BUY' ? '(highest − ATR×1.5)' : '(lowest + ATR×1.5)'}. ` +
          `Massimizza il run senza dare back tutto il guadagno.`,
      };
    }
    return null;
  });

  readonly rangeMarkers = computed(() => buildRangeMarkers(this.position()));

  readonly trendPath = computed(() => buildSparkPath(this.position().pricePath));

  /** Filled area under the price line, bounded by the entry baseline so it
   *  reads as "P&L vs open". Empty when the buffer has fewer than 2 points. */
  readonly trendArea = computed(() => {
    const path = this.position().pricePath;
    if (path.length < 2) return '';
    const min = Math.min(...path);
    const max = Math.max(...path);
    const range = max - min || 1;
    const stepX = 100 / (path.length - 1);
    const baselineY = 100 - ((this.position().entry - min) / range) * 100;
    const vertices = path.map((v, i) => {
      const x = i * stepX;
      const y = 100 - ((v - min) / range) * 100;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    }).join(' ');
    return `${vertices} L 100 ${baselineY.toFixed(2)} L 0 ${baselineY.toFixed(2)} Z`;
  });

  readonly entryBaselineY = computed(() => {
    const path = this.position().pricePath;
    if (path.length < 2) return 50;
    const min = Math.min(...path);
    const max = Math.max(...path);
    const range = max - min || 1;
    return 100 - ((this.position().entry - min) / range) * 100;
  });

  readonly priceMin = computed(() => {
    const path = this.position().pricePath;
    return path.length ? Math.min(...path) : 0;
  });

  readonly priceMax = computed(() => {
    const path = this.position().pricePath;
    return path.length ? Math.max(...path) : 0;
  });

  /** Trend agrees when direction matches gradient sign of pricePath. */
  readonly trendAgrees = computed(() => {
    const p = this.position();
    if (p.pricePath.length < 2) return null;
    const first = p.pricePath[0];
    const last = p.pricePath[p.pricePath.length - 1];
    if (first === last) return null;
    const trendUp = last > first;
    return (trendUp && p.direction === 'BUY') || (!trendUp && p.direction === 'SELL');
  });

  readonly trendLabel = computed(() => {
    const p = this.position();
    if (p.pricePath.length < 2) return '→ FLAT';
    const first = p.pricePath[0];
    const last = p.pricePath[p.pricePath.length - 1];
    if (first === last) return '→ FLAT';
    return last > first ? '↗ UP' : '↘ DOWN';
  });

  onClose(event: MouseEvent): void {
    event.stopPropagation();
    this.closeClicked.emit(this.position());
  }

  onCardClick(): void {
    this.detailsClicked.emit(this.position());
  }
}

function formatAge(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  if (h < 24) return remM > 0 ? `${h}h ${remM}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

function buildSparkPath(data: number[]): string {
  if (data.length < 2) return '';
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = 100 / (data.length - 1);
  return data
    .map((v, i) => {
      const x = i * stepX;
      const y = 100 - ((v - min) / range) * 100;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

interface RangeMarkers {
  /** Position 0..100 of entry, current, SL, TP on the visualization track. */
  entry: number;
  current: number;
  sl: number;
  tp: number;
  /** Min/max bounds used for the track (lo on left, hi on right). */
  lo: number;
  hi: number;
}

function buildRangeMarkers(p: PaperTradingPosition): RangeMarkers {
  const candidates = [p.entry, p.current, p.stopLoss, p.takeProfit].filter((v) => Number.isFinite(v));
  const lo = Math.min(...candidates);
  const hi = Math.max(...candidates);
  const range = hi - lo || 1;
  const pct = (v: number) => ((v - lo) / range) * 100;
  return {
    entry:   pct(p.entry),
    current: pct(p.current),
    sl:      pct(p.stopLoss),
    tp:      pct(p.takeProfit),
    lo,
    hi,
  };
}
