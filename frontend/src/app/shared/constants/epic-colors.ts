/**
 * Per-epic accent colors — kept in sync with the Paper Trading mockup
 * (`docs/handoff/paper-trading/mocks/Shared.jsx::ASSET_UNIVERSE`).
 *
 * Used by `models-health-panel` to tint each asset cell. Falls back to
 * the neutral token when an epic is unknown.
 */
export const EPIC_COLORS: Record<string, string> = {
  XAUUSD:   '#FFD700',
  BTCUSD:   '#F7931A',
  US500:    '#5B7FFF',
  WTIUSD:   '#3D9970',
  EURUSD:   '#0052B4',
  TSLA:     '#E31937',
  DE40:     '#FFCE00',
  NVDA:     '#76B900',
  SOLUSD:   '#9945FF',
  ETHUSD:   '#627EEA',
  BNBUSD:   '#F0B90B',
  DOGUSD:   '#C2A633',
  NATGAS:   '#A0522D',
  COPPER:   '#B87333',
  PLATINUM: '#E5E4E2',
  GBPUSD:   '#012169',
  USDJPY:   '#BC002D',
  XAGUSD:   '#C0C0C0',
  NAS100:   '#5B9BD5',
  DASHUSD:  '#008CE7',
  ICPUSD:   '#29ABE2',
  // New universe additions 2026-05-11 — brand accent colors.
  AAPL:     '#A2AAAD',
  MSFT:     '#00A4EF',
  GOOGL:    '#4285F4',
  AMZN:     '#FF9900',
  META:     '#0866FF',
  AMD:      '#ED1C24',
  USDCHF:   '#D52B1E',
  USDCAD:   '#D52B1E',
};

const NEUTRAL = '#8B949E';

export function epicColor(epic: string): string {
  return EPIC_COLORS[epic] ?? NEUTRAL;
}
