import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { MonitoringService } from './monitoring.service';
import { environment } from '../../../environments/environment';

describe('MonitoringService', () => {
  let service: MonitoringService;
  let httpMock: HttpTestingController;
  const baseUrl = `${environment.apiUrl}/monitoring`;

  const mockSignalLogsResponse = {
    success: true,
    data: {
      period: {
        start_date: '2026-01-15T00:00:00',
        end_date: '2026-02-14T00:00:00',
        days: 30
      },
      summary: {
        total_signals: 150,
        executed: 98,
        rejected: 45,
        hold: 7,
        execution_rate_pct: 65.0
      },
      by_epic: { 'XAUUSD': 80, 'BTCUSD': 70 },
      by_strategy: { 'ml_strategy': 90, 'vwap_strategy': 60 },
      by_direction: { 'LONG': 70, 'SHORT': 73, 'HOLD': 7 }
    }
  };

  const mockExecutionLogsResponse = {
    success: true,
    data: {
      period: {
        start_date: '2026-01-15T00:00:00',
        end_date: '2026-02-14T00:00:00',
        days: 30
      },
      summary: {
        total_trades: 98,
        open_positions: 3,
        closed_trades: 95,
        total_pnl: 1250.50,
        avg_pnl: 13.16,
        wins: 59,
        losses: 36,
        win_rate_pct: 62.5,
        avg_win: 45.25,
        avg_loss: -20.30,
        profit_factor: 2.1,
        avg_duration_hours: 18.5
      },
      by_epic: {
        'XAUUSD': { trades: 50, pnl: 680.0, win_rate_pct: 64.0 }
      }
    }
  };

  const mockRiskEventLogsResponse = {
    success: true,
    data: {
      period: {
        start_date: '2026-01-15T00:00:00',
        end_date: '2026-02-14T00:00:00',
        days: 30
      },
      summary: {
        total_events: 5,
        circuit_breaker_triggers: 2,
        position_limit_hits: 2,
        drawdown_limit_hits: 1,
        max_drawdown_pct: 4.5,
        avg_daily_pnl: 41.68,
        last_event: '2026-02-10T14:30:00'
      },
      by_event_type: {
        'circuit_breaker': 2,
        'position_limit': 2
      }
    }
  };

  const mockPerformanceResponse = {
    success: true,
    data: {
      period: {
        start_date: '2026-02-07T00:00:00',
        end_date: '2026-02-14T00:00:00',
        days: 7
      },
      health_score: 85,
      signals: {
        total: 50,
        execution_rate_pct: 68.0,
        top_strategy: 'ml_strategy'
      },
      execution: {
        total_trades: 34,
        open_positions: 2,
        total_pnl: 450.25,
        win_rate_pct: 64.7,
        profit_factor: 2.3
      },
      risk: {
        circuit_breaker_triggers: 1,
        max_drawdown_pct: 3.2,
        avg_daily_pnl: 64.32
      }
    }
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        MonitoringService
      ]
    });

    service = TestBed.inject(MonitoringService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('getSignalLogs', () => {
    it('should fetch signal logs with default days', async () => {
      const promise = service.getSignalLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      expect(req.request.method).toBe('GET');
      req.flush(mockSignalLogsResponse);

      await promise;

      expect(service.signalLogs()).toEqual(mockSignalLogsResponse.data);
      expect(service.loading()).toBe(false);
      expect(service.error()).toBeNull();
    });

    it('should fetch signal logs with custom days', async () => {
      const promise = service.getSignalLogs(7);

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=7`);
      req.flush(mockSignalLogsResponse);

      await promise;

      expect(service.signalLogs()).toEqual(mockSignalLogsResponse.data);
    });

    it('should handle error when fetching signal logs', async () => {
      const promise = service.getSignalLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      req.error(new ProgressEvent('Network error'));

      await promise;

      expect(service.error()).toBeTruthy();
      expect(service.loading()).toBe(false);
    });

    it('should handle unsuccessful response', async () => {
      const promise = service.getSignalLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      req.flush({ success: false });

      await promise;

      expect(service.error()).toBe('Failed to fetch signal logs');
    });
  });

  describe('getExecutionLogs', () => {
    it('should fetch execution logs', async () => {
      const promise = service.getExecutionLogs(30);

      const req = httpMock.expectOne(`${baseUrl}/logs/executions?days=30`);
      expect(req.request.method).toBe('GET');
      req.flush(mockExecutionLogsResponse);

      await promise;

      expect(service.executionLogs()).toEqual(mockExecutionLogsResponse.data);
      expect(service.error()).toBeNull();
    });

    it('should handle error when fetching execution logs', async () => {
      const promise = service.getExecutionLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/executions?days=30`);
      req.error(new ProgressEvent('Network error'));

      await promise;

      expect(service.error()).toBeTruthy();
    });
  });

  describe('getRiskEventLogs', () => {
    it('should fetch risk event logs', async () => {
      const promise = service.getRiskEventLogs(30);

      const req = httpMock.expectOne(`${baseUrl}/logs/risk-events?days=30`);
      expect(req.request.method).toBe('GET');
      req.flush(mockRiskEventLogsResponse);

      await promise;

      expect(service.riskEventLogs()).toEqual(mockRiskEventLogsResponse.data);
      expect(service.error()).toBeNull();
    });

    it('should handle error when fetching risk event logs', async () => {
      const promise = service.getRiskEventLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/risk-events?days=30`);
      req.error(new ProgressEvent('Network error'));

      await promise;

      expect(service.error()).toBeTruthy();
    });
  });

  describe('getPerformanceOverview', () => {
    it('should fetch performance overview with default days', async () => {
      const promise = service.getPerformanceOverview();

      const req = httpMock.expectOne(`${baseUrl}/stats/performance?days=7`);
      expect(req.request.method).toBe('GET');
      req.flush(mockPerformanceResponse);

      await promise;

      expect(service.performance()).toEqual(mockPerformanceResponse.data);
      expect(service.error()).toBeNull();
    });

    it('should fetch performance overview with custom days', async () => {
      const promise = service.getPerformanceOverview(14);

      const req = httpMock.expectOne(`${baseUrl}/stats/performance?days=14`);
      req.flush(mockPerformanceResponse);

      await promise;

      expect(service.performance()).toEqual(mockPerformanceResponse.data);
    });

    it('should handle error when fetching performance overview', async () => {
      const promise = service.getPerformanceOverview();

      const req = httpMock.expectOne(`${baseUrl}/stats/performance?days=7`);
      req.error(new ProgressEvent('Network error'));

      await promise;

      expect(service.error()).toBeTruthy();
    });
  });

  describe('refreshAll', () => {
    it('should refresh all monitoring data', async () => {
      const promise = service.refreshAll(30);

      // Expect 4 HTTP requests
      const signalsReq = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      const executionsReq = httpMock.expectOne(`${baseUrl}/logs/executions?days=30`);
      const riskEventsReq = httpMock.expectOne(`${baseUrl}/logs/risk-events?days=30`);
      const performanceReq = httpMock.expectOne(`${baseUrl}/stats/performance?days=7`);

      signalsReq.flush(mockSignalLogsResponse);
      executionsReq.flush(mockExecutionLogsResponse);
      riskEventsReq.flush(mockRiskEventLogsResponse);
      performanceReq.flush(mockPerformanceResponse);

      await promise;

      expect(service.signalLogs()).toEqual(mockSignalLogsResponse.data);
      expect(service.executionLogs()).toEqual(mockExecutionLogsResponse.data);
      expect(service.riskEventLogs()).toEqual(mockRiskEventLogsResponse.data);
      expect(service.performance()).toEqual(mockPerformanceResponse.data);
    });

    it('should cap performance days at 7 even if higher days provided', async () => {
      const promise = service.refreshAll(90);

      httpMock.expectOne(`${baseUrl}/logs/signals?days=90`).flush(mockSignalLogsResponse);
      httpMock.expectOne(`${baseUrl}/logs/executions?days=90`).flush(mockExecutionLogsResponse);
      httpMock.expectOne(`${baseUrl}/logs/risk-events?days=90`).flush(mockRiskEventLogsResponse);
      // Performance should be capped at 7
      const perfReq = httpMock.expectOne(`${baseUrl}/stats/performance?days=7`);
      perfReq.flush(mockPerformanceResponse);

      await promise;

      expect(service.performance()).toEqual(mockPerformanceResponse.data);
    });
  });

  describe('loading state', () => {
    it('should set loading to true during fetch', () => {
      service.getSignalLogs();

      expect(service.loading()).toBe(true);

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      req.flush(mockSignalLogsResponse);
    });

    it('should set loading to false after successful fetch', async () => {
      const promise = service.getSignalLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      req.flush(mockSignalLogsResponse);

      await promise;

      expect(service.loading()).toBe(false);
    });

    it('should set loading to false after error', async () => {
      const promise = service.getSignalLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      req.error(new ProgressEvent('error'));

      await promise;

      expect(service.loading()).toBe(false);
    });
  });

  describe('error handling', () => {
    it('should clear error before new request', async () => {
      // First request with error
      service.error.set('Previous error');

      const promise = service.getSignalLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      req.flush(mockSignalLogsResponse);

      await promise;

      expect(service.error()).toBeNull();
    });

    it('should set error message on failure', async () => {
      const promise = service.getSignalLogs();

      const req = httpMock.expectOne(`${baseUrl}/logs/signals?days=30`);
      req.error(new ProgressEvent('Network error'), { statusText: 'Network error' });

      await promise;

      expect(service.error()).toBeTruthy();
      expect(typeof service.error()).toBe('string');
    });
  });
});
