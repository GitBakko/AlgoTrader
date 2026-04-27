import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TradingService } from './trading.service';
import { environment } from '../../../environments/environment';

describe('TradingService', () => {
  let service: TradingService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(TradingService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  // ── Initial state ──

  it('should have null overview initially', () => {
    expect(service.overview()).toBeNull();
  });

  it('should have empty positions initially', () => {
    expect(service.positions()).toEqual([]);
  });

  it('should have null riskStatus initially', () => {
    expect(service.riskStatus()).toBeNull();
  });

  it('should have null paperStatus initially', () => {
    expect(service.paperStatus()).toBeNull();
  });

  it('should have empty paperPositions initially', () => {
    expect(service.paperPositions()).toEqual([]);
  });

  it('should have empty paperSignals initially', () => {
    expect(service.paperSignals()).toEqual([]);
  });

  // ── loadOverview ──

  it('should load overview and update signal', () => {
    const mockOverview = {
      equity: 10000,
      daily_pnl: 50,
      today_realized_pnl: 30,
      total_pnl: 200,
      open_positions_count: 3,
      win_rate: 0.65,
      sharpe_ratio: 1.5,
      circuit_breaker_active: false,
      trading_mode: 'PAPER',
    };

    service.loadOverview();

    const req = httpMock.expectOne(`${environment.apiUrl}/api/dashboard/overview`);
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: mockOverview });

    expect(service.overview()).toEqual(mockOverview);
  });

  // ── loadRiskStatus ──

  it('should load risk status and update signal', () => {
    const mockRisk = {
      peak_equity: 10500, current_equity: 10000,
      current_drawdown_pct: 0.0476, daily_pnl: -50,
      circuit_breaker_active: false, circuit_breaker_reason: null,
    };

    service.loadRiskStatus();

    const req = httpMock.expectOne(`${environment.apiUrl}/api/system/risk-status`);
    req.flush({ success: true, data: mockRisk });

    expect(service.riskStatus()).toEqual(mockRisk);
  });

  // ── loadPaperPositions ──

  it('should load paper positions and update signal', () => {
    const mockPositions = [
      { deal_id: 'PAPER-abc', epic: 'XAUUSD', direction: 'BUY', size: 0.1, level: 2900, stop_level: 2850, profit_level: 2950, opened_at: '2026-02-13T10:00:00Z' },
    ];

    service.loadPaperPositions();

    const req = httpMock.expectOne(`${environment.apiUrl}/api/trading/positions`);
    req.flush({ success: true, data: mockPositions });

    expect(service.paperPositions()).toEqual(mockPositions);
  });

  // ── loadPaperSignals ──

  it('should load paper signals and update signal', () => {
    const mockSignals = [
      { epic: 'BTCUSD', direction: 'BUY', confidence: 0.72, entry_price: 91000, timestamp: '2026-02-13T10:00:00Z', status: 'executed' },
    ];

    service.loadPaperSignals();

    const req = httpMock.expectOne(`${environment.apiUrl}/api/trading/signals`);
    req.flush({ success: true, data: mockSignals });

    expect(service.paperSignals()).toEqual(mockSignals);
  });

  // ── Paper Trading control ──

  it('should call start paper trading endpoint', () => {
    service.startPaperTrading().subscribe(data => {
      expect(data.message).toBeTruthy();
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/trading/start`);
    expect(req.request.method).toBe('POST');
    req.flush({ success: true, data: { running: true, message: 'Trading avviato' } });
  });

  it('should call stop paper trading endpoint', () => {
    service.stopPaperTrading().subscribe(data => {
      expect(data.message).toBeTruthy();
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/trading/stop`);
    expect(req.request.method).toBe('POST');
    req.flush({ success: true, data: { running: false, message: 'Trading fermato' } });
  });

  // ── Backtest ──

  it('should call run backtest endpoint', () => {
    const config = { epic: 'XAUUSD', timeframe: '1h' };
    service.runBacktest(config).subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/api/backtest/run`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(config);
    req.flush({ success: true, data: { id: 'bt-1', epic: 'XAUUSD', status: 'completed' } });
  });

  // ── Computed signals ──

  it('should compute openCount from positions', () => {
    expect(service.openCount()).toBe(0);
  });
});
