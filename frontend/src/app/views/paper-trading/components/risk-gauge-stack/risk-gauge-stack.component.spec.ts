import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { RiskGaugeStackComponent } from './risk-gauge-stack.component';
import type { RiskState } from '../../../../core/models/paper-trading';

const baseRisk: RiskState = {
  circuitBreakers: { status: 'OK', tripped: 0, total: 6 },
  equityFilter: { status: 'OK', dd: 19.4, threshold: 20 },
  kelly: { status: 'ATTIVO', avg: 14, win: 60.4, pnl: -28.7 },
  tradingStops: { status: 'OK', count: 3 },
};

describe('RiskGaugeStackComponent', () => {
  let fixture: ComponentFixture<RiskGaugeStackComponent>;
  let component: RiskGaugeStackComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [RiskGaugeStackComponent] }).compileComponents();
    fixture = TestBed.createComponent(RiskGaugeStackComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('risk', baseRisk);
    fixture.detectChanges();
  });

  it('renders 4 gauge rows', () => {
    const rows = fixture.debugElement.queryAll(By.css('.pv-rg__row'));
    expect(rows.length).toBe(4);
  });

  it('maps OK/ATTIVO statuses to is-ok class', () => {
    const rows = fixture.debugElement.queryAll(By.css('.pv-rg__row'));
    rows.forEach((row) => expect(row.nativeElement.classList).toContain('is-ok'));
  });

  it('renders circuit breaker tripped/total meta', () => {
    const meta = fixture.debugElement.queryAll(By.css('.pv-rg__row-meta'))[0].nativeElement as HTMLElement;
    expect(meta.textContent).toContain('0/6 tripped');
  });

  it('computes equity bar width as dd / threshold percent', () => {
    expect(component.equityBarPct()).toBeCloseTo(97, 0);
  });

  it('renders Kelly negative pnl with is-negative class', () => {
    const negative = fixture.debugElement.query(By.css('.is-negative'));
    expect(negative).toBeTruthy();
    expect((negative.nativeElement as HTMLElement).textContent).toContain('-28.7');
  });

  it('paints WARN circuit breakers row with is-warn', () => {
    fixture.componentRef.setInput('risk', { ...baseRisk, circuitBreakers: { status: 'WARN', tripped: 2, total: 6 } });
    fixture.detectChanges();
    const row = fixture.debugElement.queryAll(By.css('.pv-rg__row'))[0];
    expect(row.nativeElement.classList).toContain('is-warn');
  });
});
