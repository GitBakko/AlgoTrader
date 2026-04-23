import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { signal } from '@angular/core';
import { OperationalStripComponent } from './operational-strip.component';
import { TradingService } from '../../../../core/services/trading.service';
import { WebSocketService } from '../../../../core/services/websocket.service';
import { MarketStatusService } from '../../../../core/services/market-status.service';

describe('OperationalStripComponent', () => {
  let fixture: ComponentFixture<OperationalStripComponent>;
  let component: OperationalStripComponent;

  const tradingStub = {
    paperStatus: signal<any>({
      running: true,
      execution_mode: 'PAPER',
      iteration_count: 120,
      interval_seconds: 10,
      circuit_breakers_tripped: {},
    }),
    equityCurve: signal<any[]>([
      { date: new Date().toISOString().slice(0, 10), trade_count: 7 },
    ]),
  };

  const wsStub = {
    connected: signal(true),
    isMockPrices: signal(false),
    pricesAreFresh: signal(true),
  };

  const marketStatusStub = {
    getMarketStatus: jasmine.createSpy('getMarketStatus').and.resolveTo({
      epic: 'XAUUSD',
      is_open: true,
      status: 'TRADEABLE',
      next_open: null,
      session: { open: '00:00', close: '23:59', timezone: 'UTC' },
    }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [OperationalStripComponent],
      providers: [
        provideHttpClient(),
        { provide: TradingService, useValue: tradingStub },
        { provide: WebSocketService, useValue: wsStub },
        { provide: MarketStatusService, useValue: marketStatusStub },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(OperationalStripComponent);
    component = fixture.componentInstance;
  });

  it('creates', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('counts tripped circuit breakers from object shape', () => {
    tradingStub.paperStatus.set({
      ...tradingStub.paperStatus(),
      circuit_breakers_tripped: { daily_loss: 'Hit soglia' },
    });
    fixture.detectChanges();
    expect(component.circuitBreakersTrippedCount()).toBe(1);
  });

  it('counts tripped circuit breakers from legacy array shape', () => {
    tradingStub.paperStatus.set({
      ...tradingStub.paperStatus(),
      circuit_breakers_tripped: ['daily_loss', 'heartbeat_timeout'],
    });
    fixture.detectChanges();
    expect(component.circuitBreakersTrippedCount()).toBe(2);
  });

  it('derives trades today from equity curve last row', () => {
    fixture.detectChanges();
    expect(component.tradesToday()).toBe(7);
  });

  it('renders uptime when bot running', () => {
    tradingStub.paperStatus.set({
      running: true,
      execution_mode: 'PAPER',
      iteration_count: 360,
      interval_seconds: 10,
      circuit_breakers_tripped: {},
    });
    fixture.detectChanges();
    expect(component.paperBotUptimeText()).toBe('1h 0m');
  });

  it('falls back to dash when bot idle', () => {
    tradingStub.paperStatus.set({
      running: false,
      execution_mode: 'PAPER',
      iteration_count: 0,
      interval_seconds: 10,
      circuit_breakers_tripped: {},
    });
    fixture.detectChanges();
    expect(component.paperBotUptimeText()).toBe('—');
  });
});
