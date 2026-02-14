import { Injectable, inject, effect, signal, Injector } from '@angular/core';
import { WebSocketService } from '../../core/services/websocket.service';
import { TradingService } from '../../core/services/trading.service';

/**
 * Browser notification service for trade events and circuit breakers.
 * Requests permission on first trade event and sends native browser notifications.
 */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly ws = inject(WebSocketService);
  private readonly trading = inject(TradingService);
  private readonly injector = inject(Injector);

  readonly enabled = signal(
    typeof Notification !== 'undefined' ? Notification.permission === 'granted' : false
  );
  readonly soundEnabled = signal(true);
  private initialized = false;
  private audioCtx: AudioContext | null = null;

  /**
   * Initialize watchers for trade events and circuit breakers.
   * Call once from AppComponent.
   */
  init(): void {
    if (this.initialized) return;
    this.initialized = true;

    // Watch for new trade events via WebSocket
    effect(() => {
      const trade = this.ws.lastTrade();
      if (!trade) return;

      const isGain = trade.pnl >= 0;
      const emoji = trade.event === 'OPEN' ? (trade.direction === 'BUY' ? '\u{1F7E2}' : '\u{1F534}')
        : (isGain ? '\u{2705}' : '\u{274C}');
      const action = trade.event === 'OPEN' ? 'Aperto' : 'Chiuso';
      const pnl = trade.event === 'CLOSE' ? ` | P&L: $${trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}` : '';

      this.send(
        `${emoji} ${action}: ${trade.epic} ${trade.direction}`,
        `Deal: ${trade.deal_id}${pnl}`,
        trade.event === 'CLOSE' && !isGain ? 'loss' : 'trade',
      );
    }, { injector: this.injector });

    // Watch for circuit breaker activation
    effect(() => {
      const status = this.trading.paperStatus();
      if (!status) return;

      const tripped = status.circuit_breakers_tripped;
      if (!tripped) return;

      const reasons = Array.isArray(tripped) ? tripped : Object.keys(tripped);
      if (reasons.length > 0) {
        this.send(
          '\u{1F6A8} Circuit Breaker Attivato',
          `Motivi: ${reasons.join(', ')}`,
          'alert',
        );
      }
    }, { injector: this.injector });
  }

  /** Request browser notification permission. */
  async requestPermission(): Promise<boolean> {
    if (!('Notification' in window)) return false;
    const result = await Notification.requestPermission();
    this.enabled.set(result === 'granted');
    return result === 'granted';
  }

  /** Toggle sound alerts on/off. */
  toggleSound(): void {
    this.soundEnabled.update(v => !v);
  }

  /** Send a browser notification + optional sound. */
  private send(title: string, body: string, tag: string): void {
    // Sound alert
    if (this.soundEnabled()) {
      this.playTone(tag === 'loss' || tag === 'alert' ? 'alert' : 'success');
    }

    // Browser notification
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    new Notification(title, {
      body,
      tag,
      icon: '/assets/mantis-icon.png',
      silent: true, // we handle sound ourselves
    });
  }

  /** Play a short synthesized tone using Web Audio API. */
  private playTone(type: 'success' | 'alert'): void {
    try {
      if (!this.audioCtx) {
        this.audioCtx = new AudioContext();
      }
      const ctx = this.audioCtx;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (type === 'success') {
        // Pleasant ascending two-note chime
        osc.type = 'sine';
        osc.frequency.setValueAtTime(523, ctx.currentTime);       // C5
        osc.frequency.setValueAtTime(659, ctx.currentTime + 0.1); // E5
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.3);
      } else {
        // Descending two-note alert
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(440, ctx.currentTime);       // A4
        osc.frequency.setValueAtTime(330, ctx.currentTime + 0.15); // E4
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.35);
      }
    } catch {
      // AudioContext not available, skip silently
    }
  }
}
