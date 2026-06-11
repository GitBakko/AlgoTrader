import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeIt from '@angular/common/locales/it';
import { PositionCardComponent } from './position-card.component';
import type { PaperTradingPosition } from '../../../../core/models/paper-trading';

registerLocaleData(localeIt);

const basePosition: PaperTradingPosition = {
  id: 'p1',
  ticker: 'USDJPY',
  direction: 'BUY',
  size: 0.5,
  entry: 152.10,
  stopLoss: 151.20,
  takeProfit: 153.85,
  current: 152.65,
  pnlEur: 27.50,
  pnlPct: 0.361,
  ageSec: 1620,
  trailing: true,
  rr: 1.94,
  pricePath: [152.10, 152.20, 152.40, 152.30, 152.55, 152.65],
};

describe('PositionCardComponent', () => {
  let fixture: ComponentFixture<PositionCardComponent>;
  let component: PositionCardComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PositionCardComponent],
      providers: [{ provide: LOCALE_ID, useValue: 'it-IT' }],
    }).compileComponents();
    fixture = TestBed.createComponent(PositionCardComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('position', basePosition);
    fixture.detectChanges();
  });

  it('marks card as profit when pnlEur >= 0', () => {
    const root = fixture.debugElement.query(By.css('.pv-pc')).nativeElement as HTMLElement;
    expect(root.classList).toContain('is-profit');
  });

  it('renders ticker and direction chip', () => {
    const ticker = fixture.debugElement.query(By.css('.pv-pc__ticker')).nativeElement as HTMLElement;
    expect(ticker.textContent?.trim()).toBe('USDJPY');
    const dir = fixture.debugElement.query(By.css('.pv-pc__chip--dir')).nativeElement as HTMLElement;
    expect(dir.getAttribute('data-dir')).toBe('BUY');
  });

  it('formats age as "27m"', () => {
    expect(component.ageLabel()).toBe('27m');
  });

  it('renders TRAIL ● when trailing is on', () => {
    const trail = fixture.debugElement.query(By.css('.pv-pc__chip--trail')).nativeElement as HTMLElement;
    expect(trail.getAttribute('data-on')).toBe('true');
    expect(trail.textContent?.trim()).toBe('TRAIL ●');
  });

  it('emits closeClicked on CLOSE NOW button without bubbling card click', () => {
    const closeSpy = vi.fn();
    const detailsSpy = vi.fn();
    component.closeClicked.subscribe(closeSpy);
    component.detailsClicked.subscribe(detailsSpy);
    const btn = fixture.debugElement.query(By.css('.pv-pc__close')).nativeElement as HTMLButtonElement;
    btn.click();
    expect(closeSpy).toHaveBeenCalledWith(basePosition);
    expect(detailsSpy).not.toHaveBeenCalled();
  });

  it('emits detailsClicked on card click', () => {
    const spy = vi.fn();
    component.detailsClicked.subscribe(spy);
    const card = fixture.debugElement.query(By.css('.pv-pc')).nativeElement as HTMLElement;
    card.click();
    expect(spy).toHaveBeenCalledWith(basePosition);
  });

  it('detects trend agreement when last > first and direction is BUY', () => {
    expect(component.trendAgrees()).toBe(true);
  });

  it('marks card as loss when pnlEur < 0', () => {
    fixture.componentRef.setInput('position', { ...basePosition, pnlEur: -10, pnlPct: -0.1 });
    fixture.detectChanges();
    const root = fixture.debugElement.query(By.css('.pv-pc')).nativeElement as HTMLElement;
    expect(root.classList).toContain('is-loss');
  });

  it('places markers on the range track between 0 and 100 percent', () => {
    const m = component.rangeMarkers();
    [m.entry, m.current, m.sl, m.tp].forEach((v) => {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(100);
    });
  });
});
