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
    BTCUSD: 0,
    US500: 1,
    DE40: 1,
    XAUUSD: 2,
    XAGUSD: 3,
    WTIUSD: 2,
    NVDA: 2,
    TSLA: 2,
    EURUSD: 5,
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
