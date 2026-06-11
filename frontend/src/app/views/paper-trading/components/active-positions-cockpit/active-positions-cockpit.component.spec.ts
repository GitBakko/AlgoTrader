import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeIt from '@angular/common/locales/it';
import { ActivePositionsCockpitComponent } from './active-positions-cockpit.component';
import type { PaperTradingPosition } from '../../../../core/models/paper-trading';

registerLocaleData(localeIt);

const positionFactory = (overrides: Partial<PaperTradingPosition> = {}): PaperTradingPosition => ({
  id: 'p1',
  ticker: 'XAUUSD',
  direction: 'BUY',
  size: 0.1,
  entry: 2400,
  stopLoss: 2380,
  takeProfit: 2440,
  current: 2410,
  pnlEur: 100,
  pnlPct: 0.5,
  ageSec: 600,
  trailing: false,
  rr: 2,
  pricePath: [2400, 2405, 2410, 2412, 2410],
  ...overrides,
});

describe('ActivePositionsCockpitComponent', () => {
  let fixture: ComponentFixture<ActivePositionsCockpitComponent>;
  let component: ActivePositionsCockpitComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ActivePositionsCockpitComponent],
      providers: [{ provide: LOCALE_ID, useValue: 'it-IT' }],
    }).compileComponents();
    fixture = TestBed.createComponent(ActivePositionsCockpitComponent);
    component = fixture.componentInstance;
  });

  it('shows empty state when positions list is empty', () => {
    fixture.componentRef.setInput('positions', []);
    fixture.componentRef.setInput('signalsTotal', 42);
    fixture.detectChanges();
    const empty = fixture.debugElement.query(By.css('.pv-apc__empty'));
    expect(empty).toBeTruthy();
    const sub = fixture.debugElement.query(By.css('.pv-apc__empty-sub')).nativeElement as HTMLElement;
    expect(sub.textContent).toContain('42');
  });

  it('renders one position-card per item and total P&L sum', () => {
    fixture.componentRef.setInput('positions', [
      positionFactory({ id: 'a', pnlEur: 50 }),
      positionFactory({ id: 'b', pnlEur: -20 }),
    ]);
    fixture.componentRef.setInput('signalsTotal', 0);
    fixture.detectChanges();
    const cards = fixture.debugElement.queryAll(By.css('app-position-card'));
    expect(cards.length).toBe(2);
    expect(component.totalPnl()).toBe(30);
    const total = fixture.debugElement.query(By.css('.pv-apc__total-value')).nativeElement as HTMLElement;
    expect(total.classList).toContain('is-positive');
  });

  it('forwards closeClicked from a child position card', () => {
    const pos = positionFactory({ id: 'c' });
    fixture.componentRef.setInput('positions', [pos]);
    fixture.componentRef.setInput('signalsTotal', 0);
    fixture.detectChanges();
    const spy = vi.fn();
    component.closeRequested.subscribe(spy);
    const cardEl = fixture.debugElement.query(By.css('app-position-card'));
    cardEl.componentInstance.closeClicked.emit(pos);
    expect(spy).toHaveBeenCalledWith(pos);
  });
});
