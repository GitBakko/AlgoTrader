import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { firstValueFrom } from 'rxjs';

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

@Injectable({ providedIn: 'root' })
export class MarketStatusService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/api/markets`;

  // Cache with timestamp (60s TTL)
  private statusCache = signal<Record<string, CachedStatus>>({});

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
      const response = await firstValueFrom(
        this.http.get<{ success: boolean; data: MarketStatusResponse }>(
          `${this.baseUrl}/status/${epic}`
        )
      );

      if (response.success) {
        // Update cache
        this.statusCache.update(cache => ({
          ...cache,
          [epic]: { ...response.data, _ts: now }
        }));
        return response.data;
      }

      throw new Error('API returned success: false');
    } catch (error) {
      console.error(`Failed to fetch market status for ${epic}:`, error);

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
   * Get computed signal for multi-epic status.
   * Useful for tracking multiple assets simultaneously.
   */
  getMultiStatus(epics: string[]) {
    return computed(() => {
      const cache = this.statusCache();
      return epics.reduce((acc, epic) => {
        const cached = cache[epic];
        if (cached) {
          const { _ts, ...status } = cached;
          acc[epic] = status;
        }
        return acc;
      }, {} as Record<string, MarketStatusResponse>);
    });
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
