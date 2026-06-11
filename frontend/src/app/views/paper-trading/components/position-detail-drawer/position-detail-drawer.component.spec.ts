import type { MockedObject } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { PositionDetailDrawerComponent } from './position-detail-drawer.component';
import { SignalAuditService } from '../../../../core/services/signal-audit.service';
import type { PaperTradingPosition } from '../../../../core/models/paper-trading';

describe('PositionDetailDrawerComponent', () => {
  let fixture: ComponentFixture<PositionDetailDrawerComponent>;
  let component: PositionDetailDrawerComponent;
  let auditServiceSpy: MockedObject<SignalAuditService>;

  const baseProfitPosition: PaperTradingPosition = {
    id: '0001-deal-id',
    ticker: 'XAUUSD',
    direction: 'BUY',
    size: 0.5,
    entry: 2350.5,
    stopLoss: 2340,
    takeProfit: 2370,
    current: 2360,
    pnlEur: 47.5,
    pnlPct: 0.4,
    ageSec: 4520,
    trailing: true,
    rr: 1.94,
    pricePath: [],
  };

  beforeEach(async () => {
    auditServiceSpy = {
      openByDealId: vi.fn().mockName('SignalAuditService.openByDealId'),
      open: vi.fn().mockName('SignalAuditService.open'),
      close: vi.fn().mockName('SignalAuditService.close'),
      navigateToSignal: vi.fn().mockName('SignalAuditService.navigateToSignal'),
      openLatestByEpic: vi.fn().mockName('SignalAuditService.openLatestByEpic')
    } as unknown as MockedObject<SignalAuditService>;

    await TestBed.configureTestingModule({
      imports: [PositionDetailDrawerComponent],
      providers: [
        { provide: SignalAuditService, useValue: auditServiceSpy },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PositionDetailDrawerComponent);
    component = fixture.componentInstance;
  });

  it('renders nothing when no position is bound', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.pdd-drawer')).toBeNull();
    expect(component.isOpen()).toBe(false);
  });

  it('renders the drawer once a position is bound', () => {
    fixture.componentRef.setInput('position', baseProfitPosition);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.pdd-drawer')).not.toBeNull();
    expect(component.isOpen()).toBe(true);
  });

  it('switches active tab on click', () => {
    fixture.componentRef.setInput('position', baseProfitPosition);
    fixture.detectChanges();
    expect(component.activeTab()).toBe('overview');

    const auditTab = fixture.debugElement.query(By.css('button[data-tab="audit"]'))
      .nativeElement as HTMLButtonElement;
    auditTab.click();
    fixture.detectChanges();
    expect(component.activeTab()).toBe('audit');
  });

  it('emits closed when the close button is clicked', () => {
    fixture.componentRef.setInput('position', baseProfitPosition);
    fixture.detectChanges();
    const spy = vi.fn();
    component.closed.subscribe(spy);

    const closeBtn = fixture.debugElement.query(By.css('.pdd-close'))
      .nativeElement as HTMLButtonElement;
    closeBtn.click();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('opens the global audit drawer via SignalAuditService.openByDealId', () => {
    fixture.componentRef.setInput('position', baseProfitPosition);
    fixture.detectChanges();
    component.setTab('audit');
    fixture.detectChanges();

    const closedSpy = vi.fn();
    component.closed.subscribe(closedSpy);

    const cta = fixture.debugElement.query(By.css('.pdd-btn--primary'))
      .nativeElement as HTMLButtonElement;
    cta.click();

    expect(auditServiceSpy.openByDealId).toHaveBeenCalledWith('0001-deal-id', 'XAUUSD');
    expect(closedSpy).toHaveBeenCalledTimes(1);
  });

  it('marks profit/loss state from pnlEur sign', () => {
    fixture.componentRef.setInput('position', baseProfitPosition);
    fixture.detectChanges();
    expect(component.inProfit()).toBe(true);

    fixture.componentRef.setInput('position', { ...baseProfitPosition, pnlEur: -12.3 });
    fixture.detectChanges();
    expect(component.inProfit()).toBe(false);
  });

  it('formats age depending on duration', () => {
    fixture.componentRef.setInput('position', { ...baseProfitPosition, ageSec: 30 });
    fixture.detectChanges();
    expect(component.ageLabel()).toBe('30s');

    fixture.componentRef.setInput('position', { ...baseProfitPosition, ageSec: 600 });
    fixture.detectChanges();
    expect(component.ageLabel()).toBe('10m');

    fixture.componentRef.setInput('position', { ...baseProfitPosition, ageSec: 3 * 3600 + 25 * 60 });
    fixture.detectChanges();
    expect(component.ageLabel()).toBe('3h 25m');
  });
});
