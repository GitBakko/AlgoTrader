import { Injectable, signal, computed } from '@angular/core';
import { environment } from '../../../environments/environment';
import { PriceTick, TradeEvent, WsStatus } from '../models';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private priceWs: WebSocket | null = null;
  private tradeWs: WebSocket | null = null;
  private trainingWs: WebSocket | null = null;
  private marketsWs: WebSocket | null = null;

  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, max 60s
  private priceReconnectAttempts = 0;
  private tradeReconnectAttempts = 0;
  private trainingReconnectAttempts = 0;
  private marketsReconnectAttempts = 0;
  private readonly MAX_RECONNECT_DELAY = 60000;
  private readonly BASE_DELAY = 1000;

  /** H1-FE fix: when true, every onclose handler skips its reconnect
   *  scheduler. Set during `disconnect()` (e.g., on logout) so the
   *  resulting close events don't immediately re-open all 4 channels
   *  under the logged-out session. Each `connectX()` resets to false. */
  private intentionalDisconnect = false;

  readonly prices = signal<Record<string, PriceTick>>({});
  readonly lastTrade = signal<TradeEvent | null>(null);
  readonly connected = signal(false);
  readonly trainingUpdate = signal<any>(null);
  /** Last swap_update event received from /ws/markets (Dashboard v2). */
  readonly lastSwapUpdate = signal<{
    epic: string;
    rate_pct: number | null;
    notional: number;
    direction: string;
    source: string;
    currency: string | null;
    ts: string;
  } | null>(null);

  // Price source tracking — "broker" = real, "mock" = fake random walk
  readonly priceSource = signal<'broker' | 'mock' | 'unknown'>('unknown');
  readonly brokerReconnectAttempts = signal(0);
  readonly brokerMaxReconnectAttempts = signal(12);
  readonly isMockPrices = computed(() => this.priceSource() === 'mock');

  // Timestamp of the last received price tick (any epic)
  readonly lastPriceUpdate = signal<number>(0);

  /** Round-trip latency to the server in ms (Dashboard v2 operational strip). */
  readonly latencyMs = signal<number | null>(null);

  /** True when prices are real broker data AND received within the last 90 seconds. */
  readonly pricesAreFresh = computed(() => {
    if (this.isMockPrices()) return false;
    const lastUpdate = this.lastPriceUpdate();
    if (!lastUpdate) return false;
    return (Date.now() - lastUpdate) < 90_000;
  });

  private getReconnectDelay(attempts: number): number {
    return Math.min(this.BASE_DELAY * Math.pow(2, attempts), this.MAX_RECONNECT_DELAY);
  }

  connectPrices(): void {
    if (this.priceWs) return;
    this.intentionalDisconnect = false;
    const url = `${environment.wsUrl}/ws/prices`;
    this.priceWs = new WebSocket(url);

    this.priceWs.onopen = () => {
      this.connected.set(true);
      this.priceReconnectAttempts = 0; // Reset on successful connection
    };

    this.priceWs.onmessage = (event) => {
      const data = JSON.parse(event.data);

      // Handle ws_status messages (reconnection status + latency updates)
      if (data.type === 'ws_status') {
        const status = data as WsStatus & { latency_ms?: number | null };
        this.priceSource.set(status.price_source);
        this.brokerReconnectAttempts.set(status.reconnect_attempts);
        this.brokerMaxReconnectAttempts.set(status.max_reconnect_attempts);
        if (typeof status.latency_ms === 'number') {
          this.latencyMs.set(status.latency_ms);
        }
        return;
      }

      // Dashboard v2: server-initiated ping → echo pong so server can
      // measure the round-trip. Payload carries the server timestamp.
      if (data.type === 'ping') {
        try {
          this.priceWs?.send(JSON.stringify({
            type: 'pong',
            server_ts: data.server_ts,
            client_ts: Date.now(),
          }));
        } catch {
          // socket closed before echo — harmless
        }
        return;
      }

      // Handle heartbeat messages
      if (data.type === 'heartbeat' || data.type === 'pong') {
        return;
      }

      // Regular price tick
      const tick = data as PriceTick;
      if (tick.epic) {
        // Track price source from tick data
        if (tick.price_source) {
          this.priceSource.set(tick.price_source);
        }
        this.prices.update(current => ({ ...current, [tick.epic]: tick }));
        // Record when we last received a real price update
        if (!tick.price_source || tick.price_source === 'broker') {
          this.lastPriceUpdate.set(Date.now());
        }
      }
    };

    this.priceWs.onclose = () => {
      this.connected.set(false);
      this.priceWs = null;
      if (this.intentionalDisconnect) return;
      const delay = this.getReconnectDelay(this.priceReconnectAttempts);
      this.priceReconnectAttempts++;
      setTimeout(() => this.connectPrices(), delay);
    };

    this.priceWs.onerror = () => {
      this.priceWs?.close();
    };
  }

  connectTrades(): void {
    if (this.tradeWs) return;
    this.intentionalDisconnect = false;
    const url = `${environment.wsUrl}/ws/trades`;
    this.tradeWs = new WebSocket(url);

    this.tradeWs.onopen = () => {
      this.tradeReconnectAttempts = 0; // Reset on successful connection
    };

    this.tradeWs.onmessage = (event) => {
      const raw = JSON.parse(event.data);
      // Normalize backend "type" field to frontend "event" field
      if (raw.type === 'trade_opened') {
        raw.event = 'OPEN';
        raw.pnl = 0;
      } else if (raw.type === 'trade_closed') {
        raw.event = 'CLOSE';
      }
      if (raw.event) {
        this.lastTrade.set(raw as TradeEvent);
      }
    };

    this.tradeWs.onclose = () => {
      this.tradeWs = null;
      if (this.intentionalDisconnect) return;
      const delay = this.getReconnectDelay(this.tradeReconnectAttempts);
      this.tradeReconnectAttempts++;
      setTimeout(() => this.connectTrades(), delay);
    };

    this.tradeWs.onerror = () => {
      this.tradeWs?.close();
    };
  }

  connectTraining(): void {
    if (this.trainingWs) return;
    this.intentionalDisconnect = false;
    const url = `${environment.wsUrl}/ws/training`;
    this.trainingWs = new WebSocket(url);

    this.trainingWs.onopen = () => {
      this.trainingReconnectAttempts = 0;
    };

    this.trainingWs.onmessage = (event) => {
      const raw = JSON.parse(event.data);
      if (raw.type === 'pong') return;
      // Backend sends: { channel: "training", data: {...training status...} }
      if (raw.channel === 'training' && raw.data) {
        this.trainingUpdate.set(raw.data);
      }
    };

    this.trainingWs.onclose = () => {
      this.trainingWs = null;
      if (this.intentionalDisconnect) return;
      const delay = this.getReconnectDelay(this.trainingReconnectAttempts);
      this.trainingReconnectAttempts++;
      setTimeout(() => this.connectTraining(), delay);
    };

    this.trainingWs.onerror = () => {
      this.trainingWs?.close();
    };
  }

  /**
   * Subscribe to /ws/markets — backend pushes ``swap_update`` events when
   * paper_loop opens/closes a position or the daily snapshot job runs.
   * Components listen via ``lastSwapUpdate`` signal + effect and refresh
   * their /swap-accum cached value without polling.
   */
  connectMarkets(): void {
    if (this.marketsWs) return;
    this.intentionalDisconnect = false;
    const url = `${environment.wsUrl}/ws/markets`;
    this.marketsWs = new WebSocket(url);

    this.marketsWs.onopen = () => {
      this.marketsReconnectAttempts = 0;
    };

    this.marketsWs.onmessage = (event) => {
      try {
        const raw = JSON.parse(event.data);
        if (raw?.type === 'pong') return;
        if (raw?.type === 'swap_update' && raw.epic) {
          this.lastSwapUpdate.set(raw);
        }
      } catch {
        // swallow malformed frames
      }
    };

    this.marketsWs.onclose = () => {
      this.marketsWs = null;
      if (this.intentionalDisconnect) return;
      const delay = this.getReconnectDelay(this.marketsReconnectAttempts);
      this.marketsReconnectAttempts++;
      setTimeout(() => this.connectMarkets(), delay);
    };

    this.marketsWs.onerror = () => {
      this.marketsWs?.close();
    };
  }

  disconnect(): void {
    // H1-FE fix: flag the disconnect as intentional BEFORE calling
    // .close() so the synchronous onclose callbacks bail out without
    // scheduling a reconnect under the logged-out session. Each
    // connectX() resets the flag back to false on entry.
    this.intentionalDisconnect = true;
    this.priceWs?.close();
    this.tradeWs?.close();
    this.trainingWs?.close();
    this.marketsWs?.close();
    this.priceWs = null;
    this.tradeWs = null;
    this.trainingWs = null;
    this.marketsWs = null;
    this.connected.set(false);
    this.priceSource.set('unknown');
    this.brokerReconnectAttempts.set(0);
    this.latencyMs.set(null);
    this.priceReconnectAttempts = 0;
    this.tradeReconnectAttempts = 0;
    this.trainingReconnectAttempts = 0;
    this.marketsReconnectAttempts = 0;
  }
}
