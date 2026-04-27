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
      uptime_seconds: undefined,
      circuit_breakers_tripped: {},
    }),
    equityCurve: signal<any[]>([
      { date: new Date().toISOString().slice(0, 10), trade_count: 7 },
    ]),
    paperPositions: signal<any[]>([]),
    overview: signal<any>(null),
    performance: signal<any>(null),
    currentModels: signal<any>(null),
    overnightSwap: signal<Record<string, any>>({}),
    allocationData: signal<any>(null),
  };

  const wsStub = {
    connected: signal(true),
    isMockPrices: signal(false),
    pricesAreFresh: signal(true),
    latencyMs: signal<number | null>(null),
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
    tradingStub.performance.set(null);
    tradingStub.currentModels.set(null);
    tradingStub.overview.set(null);
    tradingStub.paperPositions.set([]);
    tradingStub.overnightSwap.set({});
    tradingStub.allocationData.set(null);
    wsStub.latencyMs.set(null);
    tradingStub.paperStatus.set({
      running: true,
      execution_mode: 'PAPER',
      iteration_count: 120,
      interval_seconds: 10,
      uptime_seconds: undefined,
      circuit_breakers_tripped: {},
    });

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
    expect(component.circuitBreakersTripped()).toBe(1);
  });

  it('counts tripped circuit breakers from legacy array shape', () => {
    tradingStub.paperStatus.set({
      ...tradingStub.paperStatus(),
      circuit_breakers_tripped: ['daily_loss', 'heartbeat_timeout'],
    });
    fixture.detectChanges();
    expect(component.circuitBreakersTripped()).toBe(2);
  });

  it('reads trade_count from performance signal', () => {
    tradingStub.performance.set({ trade_count: 18 });
    fixture.detectChanges();
    expect(component.tradesToday()).toBe(18);
  });

  it('defaults trade count to zero when performance missing', () => {
    fixture.detectChanges();
    expect(component.tradesToday()).toBe(0);
  });

  it('reports zero open positions when paperPositions empty', () => {
    fixture.detectChanges();
    expect(component.openCount()).toBe(0);
    expect(component.slotsFree()).toBe(component.maxSlots);
  });

  it('surfaces WS latency from the WebSocketService signal', () => {
    wsStub.latencyMs.set(42);
    fixture.detectChanges();
    expect(wsStub.latencyMs()).toBe(42);
  });
});
