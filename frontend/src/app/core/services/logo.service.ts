/**
 * Logo Service - Asset logo fetching and caching
 * Uses CoinGecko for crypto, Brandfetch for stocks, emoji fallback for commodities/forex
 */

import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

interface LogoCache {
  url: string;
  timestamp: number;
}

@Injectable({
  providedIn: 'root'
})
export class LogoService {
  private readonly CACHE_KEY = 'mantis-logos';
  private readonly CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours
  private cache = new Map<string, LogoCache>();

  // CoinGecko API (free tier: 30 req/min)
  private readonly COINGECKO_API = 'https://api.coingecko.com/api/v3';

  // Epic → CoinGecko ID mapping
  private readonly COIN_MAP: Record<string, string> = {
    'BTCUSD': 'bitcoin',
    'ETHUSD': 'ethereum',
    'SOLUSD': 'solana',
    'BNBUSD': 'binancecoin',
    'DOGUSD': 'dogecoin',
    'DASHUSD': 'dash',
    'ICPUSD': 'internet-computer',
  };

  // Epic → Brandfetch domain mapping (stocks)
  private readonly STOCK_MAP: Record<string, string> = {
    'NVDA': 'nvidia.com',
    'TSLA': 'tesla.com',
  };

  // Epic → Emoji fallback (commodities, forex, indices)
  private readonly EMOJI_MAP: Record<string, string> = {
    'XAUUSD': '🥇',  // Gold
    'XAGUSD': '🥈',  // Silver
    'WTIUSD': '🛢️',  // Oil
    'NATGAS': '🔥',  // Natural Gas
    'COPPER': '🔶',  // Copper
    'PLATINUM': '⚪', // Platinum
    'EURUSD': '💶',  // Euro
    'GBPUSD': '💷',  // Pound
    'USDJPY': '💴',  // Yen
    'US500': '📊',   // S&P 500
    'NAS100': '💻',  // Nasdaq
    'DE40': '🇩🇪',   // DAX
  };

  readonly logos = signal<Map<string, string>>(new Map());

  constructor(private http: HttpClient) {
    this.loadCache();
  }

  /**
   * Get logo URL for an epic
   */
  async getLogoUrl(epic: string): Promise<string> {
    // Check cache first
    const cached = this.cache.get(epic);
    if (cached && Date.now() - cached.timestamp < this.CACHE_TTL_MS) {
      return cached.url;
    }

    // Crypto assets (CoinGecko)
    if (this.COIN_MAP[epic]) {
      try {
        const url = await this.fetchCoinGeckoLogo(epic);
        this.cacheUrl(epic, url);
        return url;
      } catch {
        return this.getEmojiUrl(epic);
      }
    }

    // Stock assets (Brandfetch or emoji)
    if (this.STOCK_MAP[epic]) {
      try {
        const url = await this.fetchBrandfetchLogo(epic);
        this.cacheUrl(epic, url);
        return url;
      } catch {
        return this.getEmojiUrl(epic);
      }
    }

    // Emoji fallback
    return this.getEmojiUrl(epic);
  }

  /**
   * Preload logos for all 21 assets
   */
  async preloadAll(): Promise<void> {
    const allEpics = [
      // Crypto (7)
      'BTCUSD', 'ETHUSD', 'SOLUSD', 'BNBUSD', 'DOGUSD', 'DASHUSD', 'ICPUSD',
      // Stocks (2)
      'NVDA', 'TSLA',
      // Commodities (6)
      'XAUUSD', 'XAGUSD', 'WTIUSD', 'NATGAS', 'COPPER', 'PLATINUM',
      // Forex (3)
      'EURUSD', 'GBPUSD', 'USDJPY',
      // Indices (3)
      'US500', 'NAS100', 'DE40',
    ];

    const logoMap = new Map<string, string>();

    // Fetch in parallel (respecting rate limits)
    await Promise.allSettled(
      allEpics.map(async (epic) => {
        try {
          const url = await this.getLogoUrl(epic);
          logoMap.set(epic, url);
        } catch {
          logoMap.set(epic, this.getEmojiUrl(epic));
        }
      })
    );

    this.logos.set(logoMap);
  }

  /**
   * Fetch crypto logo from CoinGecko
   */
  private async fetchCoinGeckoLogo(epic: string): Promise<string> {
    const coinId = this.COIN_MAP[epic];
    if (!coinId) throw new Error(`No CoinGecko mapping for ${epic}`);

    const url = `${this.COINGECKO_API}/coins/${coinId}`;
    const response = await firstValueFrom(
      this.http.get<any>(url)
    );

    return response.image?.small || response.image?.thumb || this.getEmojiUrl(epic);
  }

  /**
   * Fetch stock logo from Brandfetch (fallback to emoji for now)
   * Note: Brandfetch requires API key, using emoji fallback
   */
  private async fetchBrandfetchLogo(epic: string): Promise<string> {
    // For now, use emoji fallback (Brandfetch requires paid API key)
    // In production, implement actual Brandfetch API call here
    return this.getEmojiUrl(epic);
  }

  /**
   * Get emoji fallback for an epic
   */
  private getEmojiUrl(epic: string): string {
    const emoji = this.EMOJI_MAP[epic] || '📈';
    // Use emoji as data URI (works in img src)
    return `data:image/svg+xml,${encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">
        <text x="50%" y="50%" font-size="24" text-anchor="middle" dominant-baseline="central">
          ${emoji}
        </text>
      </svg>`
    )}`;
  }

  /**
   * Cache logo URL with timestamp
   */
  private cacheUrl(epic: string, url: string): void {
    this.cache.set(epic, { url, timestamp: Date.now() });
    this.saveCache();
  }

  /**
   * Load cache from localStorage
   */
  private loadCache(): void {
    try {
      const stored = localStorage.getItem(this.CACHE_KEY);
      if (stored) {
        const data = JSON.parse(stored) as Record<string, LogoCache>;
        Object.entries(data).forEach(([epic, cache]) => {
          this.cache.set(epic, cache);
        });
      }
    } catch (error) {
      console.warn('Failed to load logo cache:', error);
    }
  }

  /**
   * Save cache to localStorage
   */
  private saveCache(): void {
    try {
      const data: Record<string, LogoCache> = {};
      this.cache.forEach((cache, epic) => {
        data[epic] = cache;
      });
      localStorage.setItem(this.CACHE_KEY, JSON.stringify(data));
    } catch (error) {
      console.warn('Failed to save logo cache:', error);
    }
  }

  /**
   * Clear expired cache entries
   */
  clearExpired(): void {
    const now = Date.now();
    this.cache.forEach((cache, epic) => {
      if (now - cache.timestamp >= this.CACHE_TTL_MS) {
        this.cache.delete(epic);
      }
    });
    this.saveCache();
  }
}
