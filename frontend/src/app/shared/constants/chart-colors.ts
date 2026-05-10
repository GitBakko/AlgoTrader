/**
 * Chart colors — palette-synced constants for Chart.js / lightweight-charts
 * that cannot consume CSS custom properties at runtime.
 *
 * These hex values MUST stay in sync with `frontend/src/scss/_palette.scss`:
 *   - $mantis-neon  : #39FF14  (accent / profit)
 *   - $mantis-green : #00d97e  (primary)
 *   - $mantis-loss  : #FF3D57
 *   - $mantis-warning: #FFB020
 *   - $mantis-cyan  : #00E5FF  (info)
 *
 * H4-FE-AUDIT / H8-FE-AUDIT / M2-FE-AUDIT / L4-FE-AUDIT: introduced to
 * stop scattered `'rgba(57, 255, 20, ...)'` and `'#00d97e'` literals
 * across performance, correlation-heatmap, backtest, and dashboard
 * template bindings. Single source of truth.
 */

export const CHART_NEON_HEX = '#39FF14';
export const CHART_GREEN_HEX = '#00d97e';
export const CHART_LOSS_HEX = '#FF3D57';
export const CHART_WARNING_HEX = '#FFB020';
export const CHART_CYAN_HEX = '#00E5FF';

export const chartProfitRgba = (alpha: number) => `rgba(57, 255, 20, ${alpha})`;
export const chartLossRgba = (alpha: number) => `rgba(255, 61, 87, ${alpha})`;
export const chartGreenRgba = (alpha: number) => `rgba(0, 217, 126, ${alpha})`;
export const chartCyanRgba = (alpha: number) => `rgba(0, 229, 255, ${alpha})`;

/** Choose profit / loss tint by sign. */
export function chartPnlRgba(value: number, alpha = 0.7): string {
  return value >= 0 ? chartProfitRgba(alpha) : chartLossRgba(alpha);
}
