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
 *  - Forex:       `flagcdn.com/w40/{cc}.png` for the quote currency
 *                  + circle-flags GitHub Pages SVG fallback
 *  - Commodities: curated inline SVG glyphs (gold bar / silver bar / oil
 *                  drop / flame / copper coin / platinum) — replaces the
 *                  emoji-only fallback so XAUUSD / WTIUSD render as
 *                  proper logos at any size.
 *  - Final tier:  inline emoji SVG that cannot fail.
 *
 * Research note (2026-04-27): no public API exposes pair-of-flag composite
 * images for FOREX. Composite SVGs with external `<image>` hrefs are
 * blocked by browsers when served as data: URIs. Single-flag (quote
 * currency) is the highest-fidelity option achievable without a backend
 * proxy. Commodity-specific image APIs (commodities-api etc.) only serve
 * price data, no glyphs — curated inline SVGs are the right answer.
 */

import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class LogoService {
  private readonly CACHE_KEY = 'mantis-logos-v5';
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

  // FOREX pairs → ISO country code for the quote currency. We render a
  // single flag (quote-side) from flagcdn.com because composite duo-flag
  // SVGs cannot reference external images when served as data: URIs.
  // Indices map to the country whose market they track.
  private readonly FLAG_MAP: Record<string, string> = {
    EURUSD: 'us',
    GBPUSD: 'us',
    USDJPY: 'jp',
    DE40:   'de',
    US500:  'us',
    NAS100: 'us',
  };

  // Commodities → curated inline SVG (small, crisp, mantis-tinted) rather
  // than emoji. Returns full data: URI ready to drop into <img src>.
  // The svgs are intentionally simple geometric glyphs so they render
  // well at 16/24/32/40 sizes.
  private readonly COMMODITY_SVG: Record<string, () => string> = {
    XAUUSD: () => this.commoditySvg('#FFD700', 'M5 18h22v6H5z M8 11h16v6H8z M11 4h10v6H11z'),
    XAGUSD: () => this.commoditySvg('#C0C0C0', 'M5 18h22v6H5z M8 11h16v6H8z M11 4h10v6H11z'),
    // WTIUSD: black oil drop on a white circle backdrop so it stays
    // legible on dark themes (otherwise the black-on-tinted-black square
    // collapses to a flat invisible square).
    WTIUSD: () => this.commoditySvg(
      '#1A1A1A',
      'M16 4 C 9 12, 6 17, 6 22 a10 10 0 0 0 20 0 c 0 -5 -3 -10 -10 -18 z',
      null,
      false,
      true,
    ),
    NATGAS: () => this.commoditySvg('#FFB020', 'M16 4 c -2 5 -6 7 -6 14 a 6 6 0 0 0 12 0 c 0 -3 -3 -5 -3 -8 c 0 -2 1 -4 -3 -6 z'),
    COPPER: () => this.commoditySvg('#B87333', null, null, true),
    PLATINUM: () => this.commoditySvg('#E5E4E2', 'M5 18h22v6H5z M8 11h16v6H8z M11 4h10v6H11z'),
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

    // FOREX pairs + indices: try a country flag for the quote-currency
    // side from flagcdn.com (fast CDN, no API key) and fall back to the
    // GitHub-hosted circle-flags SVG before the inline emoji glyph.
    if (this.FLAG_MAP[epic]) {
      const cc = this.FLAG_MAP[epic];
      return [
        `https://flagcdn.com/w40/${cc}.png`,
        `https://hatscripts.github.io/circle-flags/flags/${cc}.svg`,
        fallback,
      ];
    }

    // Commodities: inline curated SVG ahead of the generic emoji glyph
    // so XAUUSD / WTIUSD render as proper logos at any size, with no
    // external dependencies (zero CORS / rate-limit risk).
    if (this.COMMODITY_SVG[epic]) {
      return [this.COMMODITY_SVG[epic](), fallback];
    }

    return [fallback];
  }

  /** Build a small inline SVG for a commodity glyph: a tinted backdrop
   *  with an optional vector path on top (and optional accent color +
   *  "coin" mode for COPPER). Output is a `data:image/svg+xml` URI ready
   *  to use as an <img src>. */
  private commoditySvg(
    fill: string,
    path: string | null = null,
    accent: string | null = null,
    coin = false,
    whiteCircleBg = false,
  ): string {
    // Optional white rounded-square backdrop behind the path — used when
    // the glyph colour is too dark to be legible on the 10%-tinted-square
    // background (e.g. WTI's black oil drop on a dark theme would
    // otherwise vanish). Sized slightly inset (28×28 of the 32 frame) so
    // the colour-tinted ring is still visible around the white panel.
    const backdrop = whiteCircleBg
      ? `<rect x="2" y="2" width="28" height="28" rx="5" fill="#ffffff"/>`
      : '';
    const inner = coin
      ? `<circle cx="16" cy="16" r="11" fill="${fill}" stroke="${accent ?? 'rgba(0,0,0,.25)'}" stroke-width="1.5"/>
         <text x="50%" y="55%" font-size="13" font-weight="700" text-anchor="middle"
               dominant-baseline="middle" fill="rgba(0,0,0,.7)" font-family="monospace">Cu</text>`
      : path
        ? `<path d="${path}" fill="${fill}" stroke="rgba(0,0,0,.25)" stroke-width=".75"
                 stroke-linejoin="round"/>`
        : '';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
      <rect width="32" height="32" rx="6" fill="${fill}1f"/>
      ${backdrop}
      ${inner}
    </svg>`;
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
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
