import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { LiveFeedTimelineComponent } from './live-feed-timeline.component';
import type { FeedEvent } from '../../../../core/models';

describe('LiveFeedTimelineComponent', () => {
  let fixture: ComponentFixture<LiveFeedTimelineComponent>;
  let component: LiveFeedTimelineComponent;

  const sampleEvents: FeedEvent[] = [
    {
      id: 'pos-open-1',
      ts: '2026-04-27T13:30:15Z',
      kind: 'position-open',
      epic: 'XAUUSD',
      direction: 'BUY',
      confidence: 78,
      price: 2350.5,
      strategy: 'ml_ensemble',
      detail: 'aperta',
      title: 'BUY XAUUSD aperta',
      meta: 'deal-001',
      severity: 'info',
    },
    {
      id: 'signal-1',
      ts: '2026-04-27T13:30:10Z',
      kind: 'signal-reject',
      epic: 'TSLA',
      direction: 'HOLD',
      confidence: 39,
      price: 374.7,
      strategy: 'mean_reversion',
      detail: 'Total exposure 231.5% > limit 80%',
      title: 'HOLD TSLA',
      meta: 'conf 39%',
      severity: 'warning',
    },
    {
      id: 'notif-1',
      ts: '2026-04-27T13:30:05Z',
      kind: 'error',
      epic: null,
      direction: null,
      confidence: null,
      price: null,
      strategy: null,
      detail: 'connection lost',
      title: 'BROKER_ERROR',
      meta: 'connection lost',
      severity: 'critical',
    },
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LiveFeedTimelineComponent],
      providers: [provideHttpClient()],
    }).compileComponents();
    fixture = TestBed.createComponent(LiveFeedTimelineComponent);
    component = fixture.componentInstance;
  });

  it('renders empty state when no events are present', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.pv-feed__empty')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.pv-feed__list')).toBeNull();
  });

  it('renders skeleton rows when loading', () => {
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();
    const rows = fixture.nativeElement.querySelectorAll('.pv-feed__row--skeleton');
    expect(rows.length).toBeGreaterThan(0);
  });

  it('renders one row per event tagged with state and kind', () => {
    fixture.componentRef.setInput('events', sampleEvents);
    fixture.detectChanges();
    const rows = fixture.debugElement.queryAll(By.css('.pv-feed__row:not(.pv-feed__row--skeleton)'));
    expect(rows.length).toBe(3);
    expect(rows[0].nativeElement.getAttribute('data-state')).toBe('executed');
    expect(rows[1].nativeElement.getAttribute('data-state')).toBe('rejected');
    expect(rows[2].nativeElement.getAttribute('data-state')).toBe('error');
  });

  it('header counters tally executed/rejected/hold from kinds', () => {
    fixture.componentRef.setInput('events', [
      ...sampleEvents,
      {
        id: 'sig-2',
        ts: '2026-04-27T13:30:01Z',
        kind: 'signal-pending',
        epic: 'EURUSD',
        direction: 'HOLD',
        title: 'HOLD EURUSD',
      },
    ] as FeedEvent[]);
    fixture.detectChanges();
    const counts = component.counts();
    expect(counts.exec).toBe(1); // position-open counts as exec
    expect(counts.rej).toBe(1);
    expect(counts.hold).toBe(1);
  });

  it('clips to maxRows', () => {
    fixture.componentRef.setInput('events', sampleEvents);
    fixture.componentRef.setInput('maxRows', 2);
    fixture.detectChanges();
    const rows = fixture.nativeElement.querySelectorAll('.pv-feed__row:not(.pv-feed__row--skeleton)');
    expect(rows.length).toBe(2);
  });

  it('emits eventClicked with the source row', () => {
    fixture.componentRef.setInput('events', sampleEvents);
    fixture.detectChanges();
    const spy = vi.fn();
    component.eventClicked.subscribe(spy);
    const row = fixture.debugElement.query(By.css('.pv-feed__row:not(.pv-feed__row--skeleton)'))
      .nativeElement as HTMLElement;
    row.click();
    expect(spy).toHaveBeenCalledWith(sampleEvents[0]);
  });

  it('formats time as hh:mm:ss', () => {
    expect(component.formatTime('2026-04-27T08:05:09Z')).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    expect(component.formatTime(null)).toBe('--:--:--');
    expect(component.formatTime('not-a-date')).toBe('--:--:--');
  });

  it('confidenceTone follows the mock thresholds', () => {
    expect(component.confidenceTone(70)).toBe('high');
    expect(component.confidenceTone(30)).toBe('mid');
    expect(component.confidenceTone(10)).toBe('low');
    expect(component.confidenceTone(null)).toBe('none');
  });

  it('pricePrecision adapts to magnitude', () => {
    expect(component.pricePrecision(2300)).toBe('1.1-2');
    expect(component.pricePrecision(150.5)).toBe('1.2-3');
    expect(component.pricePrecision(1.234)).toBe('1.4-5');
    expect(component.pricePrecision(0.001)).toBe('1.5-6');
    expect(component.pricePrecision(null)).toBe('1.0-0');
  });

  it('renders the timeline rail when events are present', () => {
    fixture.componentRef.setInput('events', sampleEvents);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.pv-feed__rail')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.pv-feed__bullet').length).toBe(sampleEvents.length);
  });
});
