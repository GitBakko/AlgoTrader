import { Injectable, signal, computed } from '@angular/core';
import { environment } from '../../../environments/environment';
import { PriceTick, TradeEvent, WsStatus } from '../models';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private priceWs: WebSocket | null = null;
  private tradeWs: WebSocket | null = null;
  private trainingWs: WebSocket | null = null;

  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, max 60s
  private priceReconnectAttempts = 0;
  private tradeReconnectAttempts = 0;
  private trainingReconnectAttempts = 0;
  private readonly MAX_RECONNECT_DELAY = 60000;
  private readonly BASE_DELAY = 1000;

  readonly prices = signal<Record<string, PriceTick>>({});
  readonly lastTrade = signal<TradeEvent | null>(null);
  readonly connected = signal(false);
  readonly trainingUpdate = signal<any>(null);

  // Price source tracking — "broker" = real, "mock" = fake random walk
  readonly priceSource = signal<'broker' | 'mock' | 'unknown'>('unknown');
  readonly brokerReconnectAttempts = signal(0);
  readonly brokerMaxReconnectAttempts = signal(12);
  readonly isMockPrices = computed(() => this.priceSource() === 'mock');

  private getReconnectDelay(attempts: number): number {
    return Math.min(this.BASE_DELAY * Math.pow(2, attempts), this.MAX_RECONNECT_DELAY);
  }

  connectPrices(): void {
    if (this.priceWs) return;
    const url = `${environment.wsUrl}/ws/prices`;
    this.priceWs = new WebSocket(url);

    this.priceWs.onopen = () => {
      this.connected.set(true);
      this.priceReconnectAttempts = 0; // Reset on successful connection
    };

    this.priceWs.onmessage = (event) => {
      const data = JSON.parse(event.data);

      // Handle ws_status messages (reconnection status updates)
      if (data.type === 'ws_status') {
        const status = data as WsStatus;
        this.priceSource.set(status.price_source);
        this.brokerReconnectAttempts.set(status.reconnect_attempts);
        this.brokerMaxReconnectAttempts.set(status.max_reconnect_attempts);
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
      }
    };

    this.priceWs.onclose = () => {
      this.connected.set(false);
      this.priceWs = null;
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
      const delay = this.getReconnectDelay(this.trainingReconnectAttempts);
      this.trainingReconnectAttempts++;
      setTimeout(() => this.connectTraining(), delay);
    };

    this.trainingWs.onerror = () => {
      this.trainingWs?.close();
    };
  }

  disconnect(): void {
    this.priceWs?.close();
    this.tradeWs?.close();
    this.trainingWs?.close();
    this.priceWs = null;
    this.tradeWs = null;
    this.trainingWs = null;
    this.connected.set(false);
    this.priceSource.set('unknown');
    this.brokerReconnectAttempts.set(0);
    this.priceReconnectAttempts = 0;
    this.tradeReconnectAttempts = 0;
    this.trainingReconnectAttempts = 0;
  }
}
