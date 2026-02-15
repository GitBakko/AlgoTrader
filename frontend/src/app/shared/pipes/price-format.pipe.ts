import { Pipe, PipeTransform } from '@angular/core';

/**
 * Formats prices with the correct number of decimal places per asset.
 *
 * Usage: {{ price | priceFormat:'XAUUSD' }}
 *        {{ price | priceFormat:epic }}
 */
@Pipe({ name: 'priceFormat', standalone: true })
export class PriceFormatPipe implements PipeTransform {

  private static readonly DECIMALS: Record<string, number> = {
    // Crypto (high precision for low-value coins)
    BTCUSD: 0,        // ~68,000 → no decimals needed
    SOLUSD: 2,        // ~88 → 2 decimals
    ETHUSD: 1,        // ~2,085 → 1 decimal
    BNBUSD: 1,        // ~632 → 1 decimal
    DOGUSD: 6,        // ~0.11 → 6 decimals (CRITICAL!)
    DASHUSD: 2,       // ~41 → 2 decimals
    ICPUSD: 4,        // ~2.55 → 4 decimals
    // Commodities
    XAUUSD: 2,        // Gold ~2,650
    XAGUSD: 3,        // Silver ~30
    WTIUSD: 2,        // Oil ~76
    NATGAS: 3,        // Natural Gas ~3.45
    COPPER: 5,        // Copper ~4.12345
    PLATINUM: 2,      // Platinum ~950
    // Forex (high precision)
    GBPUSD: 5,        // ~1.26543
    USDJPY: 3,        // ~148.520
    EURUSD: 5,        // ~1.08234
    // Stocks
    NVDA: 2,          // ~850
    TSLA: 2,          // ~210
    // Indices
    US500: 1,         // ~5,100
    DE40: 1,          // ~17,800
  };

  transform(value: number | null | undefined, epic: string): string {
    if (value == null || isNaN(value)) return '—';
    const decimals = PriceFormatPipe.DECIMALS[epic] ?? 2;
    return value.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }
}
