import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';

export interface MarketStatusResponse {
  epic: string;
  is_open: boolean;
  status: 'TRADEABLE' | 'CLOSED' | 'SUSPENDED';
  next_open: number | null;
  session: {
    open: string;
    close: string;
    timezone: string;
  };
}

interface CachedStatus extends MarketStatusResponse {
  _ts: number;
}

/**
 * H4-FE-AUDIT / H1-CORE: migrated from raw HttpClient to ApiService.
 * H4-CORE: removed `getMultiStatus(epics)` which allocated a new
 * `computed()` per call (unbounded signal-graph growth). Callers now
 * derive multi-status locally from `statusSnapshot` plus their own
 * memoised computed.
 */
@Injectable({ providedIn: 'root' })
export class MarketStatusService {
  private readonly api = inject(ApiService);

  // Cache with timestamp (60s TTL)
  private statusCache = signal<Record<string, CachedStatus>>({});

  /** H4-CORE: read-only snapshot for downstream `computed()` derivations. */
  readonly statusSnapshot = this.statusCache.asReadonly();

  /**
   * Get market status for a specific epic.
   * Uses 60s cache to reduce API calls.
   */
  async getMarketStatus(epic: string): Promise<MarketStatusResponse> {
    const cached = this.statusCache()[epic];
    const now = Date.now();

    // Return cached status if fresh (< 60s old)
    if (cached && now - cached._ts < 60000) {
      const { _ts, ...status } = cached;
      return status;
    }

    try {
      const data = await firstValueFrom(
        this.api.get<MarketStatusResponse>(`/api/markets/status/${epic}`)
      );

      if (data) {
        this.statusCache.update(cache => ({
          ...cache,
          [epic]: { ...data, _ts: now }
        }));
        return data;
      }

      throw new Error('API returned empty data');
    } catch (error) {
      // Return cached data if available (even if expired)
      if (cached) {
        const { _ts, ...status } = cached;
        return status;
      }

      // Fallback: assume market open
      return {
        epic,
        is_open: true,
        status: 'TRADEABLE',
        next_open: null,
        session: { open: 'N/A', close: 'N/A', timezone: 'UTC' }
      };
    }
  }

  /**
   * Build a multi-status snapshot for the given epics. NOT a computed —
   * callers are expected to wrap this in their own `computed()` so the
   * memoisation is owned by the consumer (no per-call signal-graph
   * growth).
   */
  buildMultiStatus(epics: string[]): Record<string, MarketStatusResponse> {
    const cache = this.statusCache();
    return epics.reduce((acc, epic) => {
      const cached = cache[epic];
      if (cached) {
        const { _ts, ...status } = cached;
        acc[epic] = status;
      }
      return acc;
    }, {} as Record<string, MarketStatusResponse>);
  }

  /**
   * Clear the cache (useful for testing or manual refresh).
   */
  clearCache(): void {
    this.statusCache.set({});
  }

  /**
   * Get cache statistics (for debugging).
   */
  getCacheStats() {
    const cache = this.statusCache();
    const now = Date.now();

    return {
      size: Object.keys(cache).length,
      fresh: Object.values(cache).filter(c => now - c._ts < 60000).length,
      stale: Object.values(cache).filter(c => now - c._ts >= 60000).length
    };
  }
}
