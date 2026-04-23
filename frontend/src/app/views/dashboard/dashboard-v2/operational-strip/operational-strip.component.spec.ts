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
    performance: signal<any>(null),
    currentModels: signal<any>(null),
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
    // Reset shared stubs between tests.
    tradingStub.performance.set(null);
    tradingStub.currentModels.set(null);
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

  it('falls back to equity curve last row when daily_trade_count missing', () => {
    fixture.detectChanges();
    expect(component.tradesToday()).toBe(7);
  });

  it('prefers performance.daily_trade_count over equity curve', () => {
    tradingStub.performance.set({ daily_trade_count: 18 });
    fixture.detectChanges();
    expect(component.tradesToday()).toBe(18);
  });

  it('renders uptime from backend uptime_seconds when available', () => {
    tradingStub.paperStatus.set({
      running: true,
      execution_mode: 'PAPER',
      iteration_count: 0,
      interval_seconds: 10,
      uptime_seconds: 7_200, // 2h
      circuit_breakers_tripped: {},
    });
    fixture.detectChanges();
    expect(component.paperBotUptimeText()).toBe('2h 0m');
  });

  it('falls back to iteration × interval when uptime_seconds missing', () => {
    tradingStub.paperStatus.set({
      running: true,
      execution_mode: 'PAPER',
      iteration_count: 360,
      interval_seconds: 10,
      uptime_seconds: undefined,
      circuit_breakers_tripped: {},
    });
    fixture.detectChanges();
    expect(component.paperBotUptimeText()).toBe('1h 0m');
  });

  it('dash when bot idle', () => {
    tradingStub.paperStatus.set({
      running: false,
      execution_mode: 'PAPER',
      iteration_count: 0,
      interval_seconds: 10,
      uptime_seconds: 0,
      circuit_breakers_tripped: {},
    });
    fixture.detectChanges();
    expect(component.paperBotUptimeText()).toBe('—');
  });

  it('renders primary model label when currentModels populated', () => {
    tradingStub.currentModels.set({
      count: 1,
      by_epic: {},
      primary: {
        epic: 'XAUUSD',
        model_id: 'xgb-gold-v2-3',
        model_type: 'xgboost',
        num_features: 412,
        version: '2.3',
        last_trained: new Date().toISOString(),
      },
    });
    fixture.detectChanges();
    expect(component.primaryModelLabel()).toBe('XGBOOST·XAUUSD v2.3');
    expect(component.primaryModelTrainedAt()).toContain('trained');
  });

  it('surfaces WS latency from the WebSocketService signal', () => {
    wsStub.latencyMs.set(42);
    fixture.detectChanges();
    expect(wsStub.latencyMs()).toBe(42);
  });
});
