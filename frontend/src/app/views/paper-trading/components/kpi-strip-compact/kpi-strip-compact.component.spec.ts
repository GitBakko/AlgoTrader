import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeIt from '@angular/common/locales/it';
import { KpiStripCompactComponent } from './kpi-strip-compact.component';
import type { KpiStrip } from '../../../../core/models/paper-trading';

registerLocaleData(localeIt);

const baseKpi: KpiStrip = {
  pnlOpen: 124.30,
  pnlToday: -42.15,
  openCount: 3,
  winRate: 60.4,
  signalsTotal: 64,
  rr: 1.94,
  ddLive: 1.2,
  ddGate: 20,
  sparkOpen: [10, 12, 8, 14, 18, 16, 20],
  sparkToday: [-2, -3, -4, -5, -6, -5, -4],
};

describe('KpiStripCompactComponent', () => {
  let fixture: ComponentFixture<KpiStripCompactComponent>;
  let component: KpiStripCompactComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [KpiStripCompactComponent],
      providers: [{ provide: LOCALE_ID, useValue: 'it-IT' }],
    }).compileComponents();
    fixture = TestBed.createComponent(KpiStripCompactComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('kpi', baseKpi);
    fixture.detectChanges();
  });

  it('renders 6 cells', () => {
    const cells = fixture.debugElement.queryAll(By.css('.pv-kpi__cell'));
    expect(cells.length).toBe(6);
  });

  it('marks P&L Open positive when value > 0', () => {
    const cells = fixture.debugElement.queryAll(By.css('.pv-kpi__cell'));
    expect(cells[0].nativeElement.classList).toContain('is-positive');
  });

  it('marks P&L Today negative when value < 0', () => {
    const cells = fixture.debugElement.queryAll(By.css('.pv-kpi__cell'));
    expect(cells[1].nativeElement.classList).toContain('is-negative');
  });

  it('renders R:R as 1:X.XX', () => {
    const cells = fixture.debugElement.queryAll(By.css('.pv-kpi__value'));
    const rr = cells[4].nativeElement as HTMLElement;
    expect(rr.textContent?.replace(/\s+/g, ' ').trim()).toBe('1:1,94');
  });

  it('computes DD bar percent against gate', () => {
    expect(component.ddBarPct()).toBeCloseTo(6, 0);
  });

  it('falls back to USD symbol when currency unknown', () => {
    expect(component.currencySym()).toBe('$');
  });

  it('strips lowercase d suffix from currency code', () => {
    fixture.componentRef.setInput('currency', 'USDd');
    fixture.detectChanges();
    expect(component.currencySym()).toBe('$');
  });

  it('draws sparkline path for non-empty data', () => {
    expect(component.pnlOpenPath().length).toBeGreaterThan(0);
    expect(component.pnlOpenPath().startsWith('M')).toBe(true);
  });
});
