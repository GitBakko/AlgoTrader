/**
 * Dashboard v2 — shared currency helpers.
 *
 * Source of truth: DashboardOverview.currency (from broker account).
 * Capital.com demo returns e.g. "USDd" (appended "d") — the `D$` trim
 * below normalizes that back to a real ISO-4217 code.
 */
export function currencySymbol(code: string | null | undefined): string {
  // Capital.com demo appends a lowercase "d" to live ISO codes (e.g. "USDd").
  // Strip it ONLY when lowercase (don't mangle "USD" → "US").
  const raw = (code || '').trim();
  const normalized = raw.endsWith('d') ? raw.slice(0, -1).toUpperCase() : raw.toUpperCase();
  switch (normalized) {
    case 'USD': return '$';
    case 'EUR': return '€';
    case 'GBP': return '£';
    case 'JPY': return '¥';
    case 'CHF': return 'Fr';
    case 'AUD':
    case 'CAD':
    case 'NZD':
    case 'HKD':
    case 'SGD': return '$';
    default:    return normalized ? normalized + ' ' : '$';
  }
}

export function formatMoneyIt(
  n: number,
  code: string | null | undefined,
  opts: { signed?: boolean; minDec?: number; maxDec?: number } = {},
): string {
  const { signed = true, minDec = 2, maxDec = 2 } = opts;
  const sym = currencySymbol(code);
  const sign = signed ? (n > 0 ? '+' : n < 0 ? '−' : '') : '';
  const abs = Math.abs(n).toLocaleString('it-IT', {
    minimumFractionDigits: minDec,
    maximumFractionDigits: maxDec,
    // Force grouping even for 4-digit values — Italian CLDR default
    // minimumGroupingDigits=2 otherwise leaves "9012,51" ungrouped.
    useGrouping: 'always',
  } as unknown as Intl.NumberFormatOptions);
  return `${sign}${sym}${abs}`;
}

export function formatMoneyCompactIt(
  n: number,
  code: string | null | undefined,
  opts: { signed?: boolean } = {},
): string {
  const { signed = true } = opts;
  const sym = currencySymbol(code);
  const sign = signed ? (n > 0 ? '+' : n < 0 ? '−' : '') : '';
  const abs = Math.abs(n);
  if (abs >= 1000) {
    return `${sign}${sym}${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}k`;
  }
  return `${sign}${sym}${abs.toLocaleString('it-IT', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    useGrouping: 'always',
  } as unknown as Intl.NumberFormatOptions)}`;
}
