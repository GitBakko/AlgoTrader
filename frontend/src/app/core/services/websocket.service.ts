import { Injectable, signal } from '@angular/core';
import { environment } from '../../../environments/environment';
import { PriceTick, TradeEvent } from '../models';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private priceWs: WebSocket | null = null;
  private tradeWs: WebSocket | null = null;
  private reconnectDelay = 3000;

  readonly prices = signal<Record<string, PriceTick>>({});
  readonly lastTrade = signal<TradeEvent | null>(null);
  readonly connected = signal(false);

  connectPrices(): void {
    if (this.priceWs) return;
    const url = `${environment.wsUrl}/ws/prices`;
    this.priceWs = new WebSocket(url);

    this.priceWs.onopen = () => {
      this.connected.set(true);
    };

    this.priceWs.onmessage = (event) => {
      const tick: PriceTick = JSON.parse(event.data);
      this.prices.update(current => ({ ...current, [tick.epic]: tick }));
    };

    this.priceWs.onclose = () => {
      this.connected.set(false);
      this.priceWs = null;
      setTimeout(() => this.connectPrices(), this.reconnectDelay);
    };

    this.priceWs.onerror = () => {
      this.priceWs?.close();
    };
  }

  connectTrades(): void {
    if (this.tradeWs) return;
    const url = `${environment.wsUrl}/ws/trades`;
    this.tradeWs = new WebSocket(url);

    this.tradeWs.onmessage = (event) => {
      const trade: TradeEvent = JSON.parse(event.data);
      this.lastTrade.set(trade);
    };

    this.tradeWs.onclose = () => {
      this.tradeWs = null;
      setTimeout(() => this.connectTrades(), this.reconnectDelay);
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
  }
}
