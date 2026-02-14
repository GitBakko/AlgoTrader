import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { SystemLogsComponent } from './system-logs.component';
import { MonitoringService } from '../../core/services/monitoring.service';
import { signal } from '@angular/core';

describe('SystemLogsComponent', () => {
  let component: SystemLogsComponent;
  let fixture: ComponentFixture<SystemLogsComponent>;
  let monitoringService: jasmine.SpyObj<MonitoringService>;

  const mockPerformance = {
    period: {
      start_date: '2026-01-15T00:00:00',
      end_date: '2026-02-14T00:00:00',
      days: 30
    },
    health_score: 85,
    signals: {
      total: 150,
      execution_rate_pct: 65.0,
      top_strategy: 'ml_strategy'
    },
    execution: {
      total_trades: 98,
      open_positions: 3,
      total_pnl: 1250.50,
      win_rate_pct: 62.5,
      profit_factor: 2.1
    },
    risk: {
      circuit_breaker_triggers: 2,
      max_drawdown_pct: 4.5,
      avg_daily_pnl: 41.68
    }
  };

  const mockSignalLogs = {
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
  };

  const mockExecutionLogs = {
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
      'XAUUSD': { trades: 50, pnl: 680.0, win_rate_pct: 64.0 },
      'BTCUSD': { trades: 48, pnl: 570.5, win_rate_pct: 60.4 }
    }
  };

  const mockRiskEventLogs = {
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
      'position_limit': 2,
      'drawdown_limit': 1
    }
  };

  beforeEach(async () => {
    const monitoringServiceSpy = jasmine.createSpyObj('MonitoringService', [
      'refreshAll',
      'getSignalLogs',
      'getExecutionLogs',
      'getRiskEventLogs',
      'getPerformanceOverview'
    ]);

    // Setup signal properties
    monitoringServiceSpy.loading = signal(false);
    monitoringServiceSpy.error = signal(null);
    monitoringServiceSpy.performance = signal(mockPerformance);
    monitoringServiceSpy.signalLogs = signal(mockSignalLogs);
    monitoringServiceSpy.executionLogs = signal(mockExecutionLogs);
    monitoringServiceSpy.riskEventLogs = signal(mockRiskEventLogs);

    // Setup spy return values
    monitoringServiceSpy.refreshAll.and.returnValue(Promise.resolve());

    await TestBed.configureTestingModule({
      imports: [SystemLogsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: MonitoringService, useValue: monitoringServiceSpy }
      ]
    }).compileComponents();

    monitoringService = TestBed.inject(MonitoringService) as jasmine.SpyObj<MonitoringService>;
    fixture = TestBed.createComponent(SystemLogsComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load data on init', () => {
    fixture.detectChanges();
    expect(monitoringService.refreshAll).toHaveBeenCalledWith(30);
  });

  it('should display health score', () => {
    fixture.detectChanges();
    // Check that performance data is available in component
    expect(component.performance()).toBeTruthy();
    expect(component.performance()?.health_score).toBe(85);
  });

  it('should calculate health score color correctly', () => {
    expect(component.healthScoreColor()).toBe('success'); // 85 >= 85

    monitoringService.performance.set({ ...mockPerformance, health_score: 75 });
    expect(component.healthScoreColor()).toBe('warning'); // 70 <= 75 < 85

    monitoringService.performance.set({ ...mockPerformance, health_score: 50 });
    expect(component.healthScoreColor()).toBe('danger'); // 50 < 70
  });

  it('should calculate health score text correctly', () => {
    expect(component.healthScoreText()).toBe('Excellent');

    monitoringService.performance.set({ ...mockPerformance, health_score: 75 });
    expect(component.healthScoreText()).toBe('Good');

    monitoringService.performance.set({ ...mockPerformance, health_score: 55 });
    expect(component.healthScoreText()).toBe('Fair');

    monitoringService.performance.set({ ...mockPerformance, health_score: 40 });
    expect(component.healthScoreText()).toBe('Poor');
  });

  it('should compute epic breakdown correctly', () => {
    const breakdown = component.epicBreakdown();

    expect(breakdown.length).toBe(2);
    expect(breakdown.find(e => e.epic === 'XAUUSD')).toEqual({
      epic: 'XAUUSD',
      signals: 80,
      trades: 50,
      pnl: 680.0,
      win_rate: 64.0
    });
  });

  it('should compute strategy breakdown correctly', () => {
    const breakdown = component.strategyBreakdown();

    expect(breakdown.length).toBe(2);
    expect(breakdown).toContain({ strategy: 'ml_strategy', count: 90 });
    expect(breakdown).toContain({ strategy: 'vwap_strategy', count: 60 });
  });

  it('should compute risk events breakdown correctly', () => {
    const breakdown = component.riskEventsBreakdown();

    expect(breakdown.length).toBe(3);
    expect(breakdown).toContain({ type: 'Circuit Breaker', count: 2 });
    expect(breakdown).toContain({ type: 'Position Limit', count: 2 });
    expect(breakdown).toContain({ type: 'Drawdown Limit', count: 1 });
  });

  it('should change date range', async () => {
    await component.onDateRangeChange(7);
    expect(component.selectedDays()).toBe(7);
    expect(monitoringService.refreshAll).toHaveBeenCalledWith(7);
  });

  it('should refresh data', async () => {
    await component.refresh();
    expect(monitoringService.refreshAll).toHaveBeenCalled();
  });

  it('should format currency correctly', () => {
    expect(component.formatCurrency(1250.50)).toBe('$1,250.50');
    expect(component.formatCurrency(-500.25)).toBe('-$500.25');
  });

  it('should format percent correctly', () => {
    expect(component.formatPercent(65.0)).toBe('65.00%');
    expect(component.formatPercent(4.567)).toBe('4.57%');
  });

  it('should format number correctly', () => {
    expect(component.formatNumber(1500)).toBe('1,500');
    expect(component.formatNumber(1500000)).toBe('1,500,000');
  });

  it('should format event type correctly', () => {
    expect(component.formatEventType('circuit_breaker')).toBe('Circuit Breaker');
    expect(component.formatEventType('position_limit')).toBe('Position Limit');
    expect(component.formatEventType('drawdown_limit')).toBe('Drawdown Limit');
  });

  it('should show loading state', () => {
    monitoringService.loading.set(true);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.spinner-border')).toBeTruthy();
    expect(compiled.textContent).toContain('Loading monitoring data...');
  });

  it('should show error state', () => {
    monitoringService.loading.set(false);
    monitoringService.error.set('Connection failed');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Error:');
    expect(compiled.textContent).toContain('Connection failed');
  });

  it('should display all 9 performance metrics', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    // Health score
    expect(compiled.textContent).toContain('85');

    // Signals
    expect(compiled.textContent).toContain('150');
    expect(compiled.textContent).toContain('65.00%');

    // Execution
    expect(compiled.textContent).toContain('98');
    expect(compiled.textContent).toContain('1,250.50');
    expect(compiled.textContent).toContain('62.50%');

    // Risk
    expect(compiled.textContent).toContain('2'); // circuit breakers
    expect(compiled.textContent).toContain('4.50%'); // max DD
  });

  it('should have correct theme colors', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    // Check that MANTIS green badge exists
    const successBadges = compiled.querySelectorAll('c-badge[color="success"]');
    expect(successBadges.length).toBeGreaterThan(0);
  });
});
