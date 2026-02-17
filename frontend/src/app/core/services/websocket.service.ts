import { Injectable, signal } from '@angular/core';
import { environment } from '../../../environments/environment';
import { PriceTick, TradeEvent } from '../models';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private priceWs: WebSocket | null = null;
  private tradeWs: WebSocket | null = null;

  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, max 60s
  private priceReconnectAttempts = 0;
  private tradeReconnectAttempts = 0;
  private readonly MAX_RECONNECT_DELAY = 60000;
  private readonly BASE_DELAY = 1000;

  readonly prices = signal<Record<string, PriceTick>>({});
  readonly lastTrade = signal<TradeEvent | null>(null);
  readonly connected = signal(false);

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
      const tick: PriceTick = JSON.parse(event.data);
      this.prices.update(current => ({ ...current, [tick.epic]: tick }));
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

  disconnect(): void {
    this.priceWs?.close();
    this.tradeWs?.close();
    this.priceWs = null;
    this.tradeWs = null;
    this.connected.set(false);
    this.priceReconnectAttempts = 0;
    this.tradeReconnectAttempts = 0;
  }
}
