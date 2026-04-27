import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { SignalsHeatmapComponent } from './signals-heatmap.component';
import type { TradingSignal, PaperPosition } from '../../../../core/models';

describe('SignalsHeatmapComponent', () => {
  let fixture: ComponentFixture<SignalsHeatmapComponent>;
  let component: SignalsHeatmapComponent;

  const universe: readonly string[] = [
    'XAUUSD', 'BTCUSD', 'EURUSD', 'TSLA', 'NVDA', 'USDJPY',
  ];

  function makeSignal(epic: string, ts: string, direction: string, status: string, conf = 0.7): TradingSignal {
    return {
      id: 1,
      epic,
      direction,
      confidence: conf,
      signal_class: 0,
      entry_price: 100,
      suggested_stop: null,
      suggested_tp: null,
      regime: null,
      timestamp: ts,
      status,
    };
  }

  function makePosition(epic: string): PaperPosition {
    return {
      deal_id: `deal-${epic}`,
      epic,
      direction: 'BUY',
      size: 1,
      level: 100,
      stop_level: null,
      profit_level: null,
      opened_at: new Date().toISOString(),
    } as PaperPosition;
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SignalsHeatmapComponent],
      providers: [provideHttpClient()],
    }).compileComponents();
    fixture = TestBed.createComponent(SignalsHeatmapComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('epics', universe);
  });

  it('renders one cell per epic by default and exposes the count', () => {
    fixture.detectChanges();
    const cells = fixture.nativeElement.querySelectorAll('.pv-heatmap__cell:not(.pv-heatmap__cell--skeleton)');
    expect(cells.length).toBe(universe.length);
    const count = fixture.nativeElement.querySelector('.pv-heatmap__count') as HTMLElement;
    expect(count.textContent?.trim()).toBe(String(universe.length));
  });

  it('reduces signals to the latest per epic and tags state correctly', () => {
    fixture.componentRef.setInput('signals', [
      makeSignal('XAUUSD', '2026-01-01T10:00:00Z', 'BUY', 'EXECUTED'),
      makeSignal('XAUUSD', '2026-01-01T11:00:00Z', 'SELL', 'EXECUTED'),
      makeSignal('TSLA', '2026-01-01T09:00:00Z', 'HOLD', 'REJECTED'),
    ]);
    fixture.detectChanges();
    const xau = component.allCells().find((c) => c.epic === 'XAUUSD')!;
    expect(xau.direction).toBe('SELL');
    expect(xau.state).toBe('executed');
    const tsla = component.allCells().find((c) => c.epic === 'TSLA')!;
    expect(tsla.direction).toBe('HOLD');
    expect(tsla.state).toBe('rejected');
  });

  it('marks epic with an open position as live regardless of latest status', () => {
    fixture.componentRef.setInput('signals', [
      makeSignal('NVDA', '2026-01-01T10:00:00Z', 'SELL', 'REJECTED'),
    ]);
    fixture.componentRef.setInput('positions', [makePosition('NVDA')]);
    fixture.detectChanges();
    const nvda = component.allCells().find((c) => c.epic === 'NVDA')!;
    expect(nvda.state).toBe('live');
  });

  it('returns "none" state for epics without any signal', () => {
    fixture.detectChanges();
    const eur = component.allCells().find((c) => c.epic === 'EURUSD')!;
    expect(eur.state).toBe('none');
    expect(eur.confidence).toBeNull();
    expect(eur.direction).toBe('—');
  });

  it('filter "active" hides hold cells and keeps executed/rejected/live/closed', () => {
    fixture.componentRef.setInput('signals', [
      makeSignal('XAUUSD', '2026-01-01T10:00:00Z', 'BUY', 'EXECUTED'),
      makeSignal('TSLA', '2026-01-01T11:00:00Z', 'HOLD', 'REJECTED'),
      makeSignal('BTCUSD', '2026-01-01T12:00:00Z', 'HOLD', 'PENDING'),
    ]);
    fixture.detectChanges();
    component.setFilter('active');
    fixture.detectChanges();
    const visibleEpics = component.cells().map((c) => c.epic).sort();
    expect(visibleEpics).toEqual(['TSLA', 'XAUUSD']);
  });

  it('filter "hold" only keeps cells whose latest is HOLD', () => {
    fixture.componentRef.setInput('signals', [
      makeSignal('XAUUSD', '2026-01-01T10:00:00Z', 'BUY', 'EXECUTED'),
      makeSignal('USDJPY', '2026-01-01T11:00:00Z', 'HOLD', 'PENDING'),
    ]);
    fixture.detectChanges();
    component.setFilter('hold');
    fixture.detectChanges();
    const visible = component.cells().map((c) => c.epic);
    expect(visible).toContain('USDJPY');
    expect(visible).not.toContain('XAUUSD');
  });

  it('confidenceTone maps thresholds to high/mid/low/none', () => {
    expect(component.confidenceTone(70)).toBe('high');
    expect(component.confidenceTone(30)).toBe('mid');
    expect(component.confidenceTone(10)).toBe('low');
    expect(component.confidenceTone(null)).toBe('none');
  });

  it('emits cellClicked with the cell payload', () => {
    fixture.componentRef.setInput('signals', [
      makeSignal('BTCUSD', '2026-01-01T10:00:00Z', 'BUY', 'EXECUTED'),
    ]);
    fixture.detectChanges();
    const spy = jasmine.createSpy('cellClicked');
    component.cellClicked.subscribe(spy);
    const cells = fixture.debugElement.queryAll(By.css('.pv-heatmap__cell'));
    const btcCell = cells.find((c) => c.nativeElement.getAttribute('aria-label')?.startsWith('BTCUSD'))!;
    btcCell.nativeElement.click();
    const arg = spy.calls.mostRecent().args[0];
    expect(arg.epic).toBe('BTCUSD');
    expect(arg.direction).toBe('BUY');
  });

  it('renders skeleton placeholders when loading', () => {
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();
    const skeletons = fixture.nativeElement.querySelectorAll('.pv-heatmap__cell--skeleton');
    expect(skeletons.length).toBe(universe.length);
  });
});
