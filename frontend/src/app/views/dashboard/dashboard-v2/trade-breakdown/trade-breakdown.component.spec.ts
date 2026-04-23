import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { TradeBreakdownComponent } from './trade-breakdown.component';
import { TradeBreakdownDay } from './trade-breakdown.types';
import { TimeframeService } from '../../../../core/services/timeframe.service';

function day(date: string, buyTp = 0, buySl = 0, buyGo = 0, sellTp = 0, sellSl = 0, sellGo = 0, pnlB = 0, pnlS = 0): TradeBreakdownDay {
  return {
    date,
    buy:  { tp: buyTp, sl: buySl, going: buyGo, pnl: pnlB },
    sell: { tp: sellTp, sl: sellSl, going: sellGo, pnl: pnlS },
  };
}

describe('TradeBreakdownComponent', () => {
  let fixture: ComponentFixture<TradeBreakdownComponent>;
  let component: TradeBreakdownComponent;
  let tf: TimeframeService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TradeBreakdownComponent],
      providers: [provideHttpClient()],
    }).compileComponents();

    fixture = TestBed.createComponent(TradeBreakdownComponent);
    component = fixture.componentInstance;
    tf = TestBed.inject(TimeframeService);
  });

  it('creates', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('flags backend missing when days input is null', () => {
    fixture.detectChanges();
    expect(component.isBackendMissing()).toBeTrue();
    expect(component.hasData()).toBeFalse();
    const banner = fixture.nativeElement.querySelector('.tb-todo');
    expect(banner).toBeTruthy();
    expect(banner.textContent).toContain('Backend endpoint pending');
  });

  it('renders columns when data provided', () => {
    const data = [
      day('2026-04-20', 3, 1, 0, 2, 2, 0, 180, -40),
      day('2026-04-21', 4, 0, 1, 1, 3, 0, 220, -70),
    ];
    fixture.componentRef.setInput('days', data);
    fixture.detectChanges();
    expect(component.hasData()).toBeTrue();
    expect(component.isBackendMissing()).toBeFalse();
    expect(fixture.nativeElement.querySelectorAll('.tb-col').length).toBe(4);
  });

  it('max stack equals the tallest side across days', () => {
    const data = [
      day('2026-04-20', 3, 1, 0, 2, 2, 0),
      day('2026-04-21', 4, 0, 1, 1, 3, 0),
    ];
    fixture.componentRef.setInput('days', data);
    fixture.detectChanges();
    expect(component.maxStack()).toBe(5); // 4+0+1 = 5 BUY day 2
  });

  it('defaults focus to last day P&L and open-count', () => {
    const data = [
      day('2026-04-20', 1, 0, 0, 0, 0, 0, 50, 0),
      day('2026-04-21', 2, 0, 1, 1, 1, 1, 80, -30),
    ];
    fixture.componentRef.setInput('days', data);
    fixture.detectChanges();
    expect(component.focusedDayPnl()).toBe(50);
    expect(component.focusedStillOpen()).toBe(2);
  });

  it('follows explicit focus index when set', () => {
    const data = [
      day('2026-04-20', 1, 0, 0, 0, 0, 0, 10, 0),
      day('2026-04-21', 0, 0, 0, 1, 0, 0, 0, 20),
    ];
    fixture.componentRef.setInput('days', data);
    component.setFocus(0);
    fixture.detectChanges();
    expect(component.focusedDayPnl()).toBe(10);
  });

  it('uses TimeframeService label in header', () => {
    tf.set('7D');
    fixture.detectChanges();
    expect(component.timeframeLabel()).toBe('7D');
  });
});
