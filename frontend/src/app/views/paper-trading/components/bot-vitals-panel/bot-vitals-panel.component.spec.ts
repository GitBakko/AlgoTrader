import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { BotVitalsPanelComponent } from './bot-vitals-panel.component';
import type { BotVitals } from '../../../../core/models/paper-trading';

const baseVitals: BotVitals = {
  state: 'RUNNING',
  uptime: '4h 12m',
  lastTickAgo: 1.2,
  iterations: 9,
  intervalSec: 900,
  errors: 0,
  signals: { total: 64, executed: 2, rejected: 1, hold: 61, conversion: 0.037 },
};

describe('BotVitalsPanelComponent', () => {
  let fixture: ComponentFixture<BotVitalsPanelComponent>;
  let component: BotVitalsPanelComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [BotVitalsPanelComponent] }).compileComponents();
    fixture = TestBed.createComponent(BotVitalsPanelComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('vitals', baseVitals);
    fixture.detectChanges();
  });

  it('renders BOT VITALS label with RUNNING state', () => {
    const pill = fixture.debugElement.query(By.css('.pv-bv__pill')).nativeElement as HTMLElement;
    expect(pill.getAttribute('data-state')).toBe('RUNNING');
    expect(pill.textContent).toContain('BOT VITALS');
  });

  it('renders 2x2 stat grid with iterations, interval, uptime, errors', () => {
    const stats = fixture.debugElement.queryAll(By.css('.pv-bv__stat-value'));
    expect(stats.length).toBe(4);
    expect(stats[0].nativeElement.textContent.trim()).toBe('9');
    expect(stats[1].nativeElement.textContent.trim()).toBe('15m');
    expect(stats[2].nativeElement.textContent.trim()).toBe('4h 12m');
    expect(stats[3].nativeElement.textContent.trim()).toBe('0');
  });

  it('formats lastTickAgo under 60s as "x.xs"', () => {
    expect(component.tickLabel()).toBe('1.2s');
  });

  it('formats interval ≥60 as minutes', () => {
    fixture.componentRef.setInput('vitals', { ...baseVitals, intervalSec: 30 });
    fixture.detectChanges();
    expect(component.intervalLabel()).toBe('30s');
  });

  it('renders signals total / executed and conversion percentage', () => {
    const total = fixture.debugElement.query(By.css('.pv-bv__signals-total')).nativeElement as HTMLElement;
    const exec = fixture.debugElement.query(By.css('.pv-bv__signals-exec')).nativeElement as HTMLElement;
    const conv = fixture.debugElement.query(By.css('.pv-bv__signals-conv')).nativeElement as HTMLElement;
    expect(total.textContent?.trim()).toBe('64');
    expect(exec.textContent?.trim()).toBe('2');
    expect(conv.textContent).toContain('3.7%');
  });

  it('paints errors red when above 0', () => {
    fixture.componentRef.setInput('vitals', { ...baseVitals, errors: 3 });
    fixture.detectChanges();
    const errors = fixture.debugElement.queryAll(By.css('.pv-bv__stat-value'))[3].nativeElement as HTMLElement;
    expect(errors.classList).toContain('is-loss');
  });
});
