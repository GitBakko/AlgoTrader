/**
 * Logo Service — resilient asset logo URLs.
 *
 * The previous implementation called the CoinGecko REST API which is
 * rate-limited (30 req/min on the free tier) and unreliable from a
 * browser due to occasional CORS failures, causing every stock/crypto
 * card to fall back to the emoji silhouette. This rewrite removes API
 * calls entirely: each epic resolves to an ordered list of direct
 * image URLs, and the EpicLogoComponent steps through them in `onError`
 * until one loads. The final entry is always an inline SVG emoji that
 * cannot fail.
 *
 * Sources used (all free, no API key required):
 *  - Crypto:      `assets.coincap.io/assets/icons/{symbol}@2x.png`
 *                  + `cryptologos.cc/logos/{slug}-{ticker}-logo.svg`
 *                  + `cryptoicons.org/api/icon/{symbol}/64`
 *  - Stocks:      `logo.clearbit.com/{domain}` (free tier, returns image)
 *                  + `eodhd.com/img/logos/US/{ticker}.png`
 *  - Forex/idx/   inline SVG emoji (already in the previous impl)
 *    commodities
 */

import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class LogoService {
  private readonly CACHE_KEY = 'mantis-logos-v2';
  private readonly CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  private cache = new Map<string, { urls: string[]; ts: number }>();

  // Crypto epics → (CoinCap symbol, cryptologos slug, cryptoicons symbol)
  private readonly CRYPTO_MAP: Record<string, { symbol: string; slug?: string; ticker?: string }> = {
    BTCUSD:  { symbol: 'btc', slug: 'bitcoin',           ticker: 'btc' },
    ETHUSD:  { symbol: 'eth', slug: 'ethereum',          ticker: 'eth' },
    SOLUSD:  { symbol: 'sol', slug: 'solana',            ticker: 'sol' },
    BNBUSD:  { symbol: 'bnb', slug: 'bnb',               ticker: 'bnb' },
    DOGUSD:  { symbol: 'doge', slug: 'dogecoin',         ticker: 'doge' },
    DASHUSD: { symbol: 'dash', slug: 'dash',             ticker: 'dash' },
    ICPUSD:  { symbol: 'icp', slug: 'internet-computer', ticker: 'icp' },
  };

  // Stock epics → primary domain (clearbit lookup)
  private readonly STOCK_MAP: Record<string, string> = {
    NVDA: 'nvidia.com',
    TSLA: 'tesla.com',
  };

  // Inline emoji fallback for forex/commodities/indices and as final tier.
  private readonly EMOJI_MAP: Record<string, string> = {
    XAUUSD:   '🥇',
    XAGUSD:   '🥈',
    WTIUSD:   '🛢️',
    NATGAS:   '🔥',
    COPPER:   '🟠',
    PLATINUM: '⚪',
    EURUSD:   '💶',
    GBPUSD:   '💷',
    USDJPY:   '💴',
    US500:    '📊',
    NAS100:   '💻',
    DE40:     '🇩🇪',
  };

  // Per-epic accent color for the SVG emoji bg (mantis palette mirror).
  private readonly ACCENT_MAP: Record<string, string> = {
    XAUUSD: '#FFD700',
    XAGUSD: '#C0C0C0',
    BTCUSD: '#F7931A',
    ETHUSD: '#627EEA',
    SOLUSD: '#9945FF',
    BNBUSD: '#F0B90B',
    DOGUSD: '#C2A633',
    NVDA:   '#76B900',
    TSLA:   '#E31937',
    DE40:   '#FFCE00',
    NAS100: '#5B9BD5',
    US500:  '#5B7FFF',
  };

  readonly logos = signal<Map<string, string[]>>(new Map());

  constructor() {
    this.loadCache();
  }

  /**
   * Resolve a priority-ordered list of logo URLs for an epic. Caller
   * (EpicLogoComponent) walks the list in `onError`. The last entry is
   * always an inline SVG that cannot fail.
   */
  getLogoUrls(epic: string): string[] {
    const cached = this.cache.get(epic);
    if (cached && Date.now() - cached.ts < this.CACHE_TTL_MS) {
      return cached.urls;
    }
    const urls = this.buildUrls(epic);
    this.cache.set(epic, { urls, ts: Date.now() });
    this.saveCache();
    return urls;
  }

  /** Backwards-compat shim — older callers asked for a single URL. */
  async getLogoUrl(epic: string): Promise<string> {
    const urls = this.getLogoUrls(epic);
    return urls[0] ?? this.emojiSvg(epic);
  }

  private buildUrls(epic: string): string[] {
    const fallback = this.emojiSvg(epic);

    if (this.CRYPTO_MAP[epic]) {
      const { symbol, slug, ticker } = this.CRYPTO_MAP[epic];
      const out: string[] = [
        `https://assets.coincap.io/assets/icons/${symbol}@2x.png`,
      ];
      if (slug && ticker) {
        out.push(`https://cryptologos.cc/logos/${slug}-${ticker}-logo.svg?v=035`);
      }
      out.push(`https://cryptoicons.org/api/icon/${symbol}/64`);
      out.push(fallback);
      return out;
    }

    if (this.STOCK_MAP[epic]) {
      const domain = this.STOCK_MAP[epic];
      return [
        `https://logo.clearbit.com/${domain}`,
        `https://eodhd.com/img/logos/US/${epic}.png`,
        fallback,
      ];
    }

    return [fallback];
  }

  /** Render an inline SVG containing the emoji + tinted backdrop. */
  private emojiSvg(epic: string): string {
    const emoji = this.EMOJI_MAP[epic] ?? '📈';
    const accent = this.ACCENT_MAP[epic] ?? '#39FF14';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
      <rect width="32" height="32" rx="6" fill="${accent}1f"/>
      <text x="50%" y="55%" font-size="18" text-anchor="middle" dominant-baseline="middle">${emoji}</text>
    </svg>`;
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
  }

  private loadCache(): void {
    try {
      const stored = localStorage.getItem(this.CACHE_KEY);
      if (!stored) return;
      const data = JSON.parse(stored) as Record<string, { urls: string[]; ts: number }>;
      for (const [epic, value] of Object.entries(data)) {
        this.cache.set(epic, value);
      }
    } catch {
      // ignore — cache is best-effort
    }
  }

  private saveCache(): void {
    try {
      const data: Record<string, { urls: string[]; ts: number }> = {};
      this.cache.forEach((value, epic) => {
        data[epic] = value;
      });
      localStorage.setItem(this.CACHE_KEY, JSON.stringify(data));
    } catch {
      // ignore — quota or disabled storage
    }
  }
}
