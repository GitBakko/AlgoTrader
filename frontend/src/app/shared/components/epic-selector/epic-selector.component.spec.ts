import { ComponentFixture, TestBed } from '@angular/core/testing';
import { EpicSelectorComponent, MarketStatus } from './epic-selector.component';

describe('EpicSelectorComponent', () => {
  let component: EpicSelectorComponent;
  let fixture: ComponentFixture<EpicSelectorComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EpicSelectorComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(EpicSelectorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display placeholder when no epic selected', () => {
    const button = fixture.nativeElement.querySelector('button');
    expect(button.textContent.trim()).toBe('Select Asset');
  });

  it('should display selected epic', () => {
    fixture.componentRef.setInput('epics', ['XAUUSD', 'BTCUSD']);
    component.selectedEpic.set('XAUUSD');
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('button');
    expect(button.textContent.trim()).toBe('XAUUSD');
  });

  it('should show closed badge for closed markets', () => {
    const marketStatus: Record<string, MarketStatus> = {
      'XAUUSD': { is_open: false, status: 'CLOSED', next_open: Date.now() + 3600000 }
    };

    fixture.componentRef.setInput('epics', ['XAUUSD', 'BTCUSD']);
    fixture.componentRef.setInput('marketStatus', marketStatus);
    fixture.detectChanges();

    // Open dropdown
    const button = fixture.nativeElement.querySelector('button');
    button.click();
    fixture.detectChanges();

    const badges = fixture.nativeElement.querySelectorAll('.badge-danger');
    expect(badges.length).toBe(1);
    expect(badges[0].textContent.trim()).toBe('CLOSED');
  });

  it('should emit selection when epic clicked', () => {
    fixture.componentRef.setInput('epics', ['XAUUSD', 'BTCUSD']);
    fixture.detectChanges();

    component.onSelect('BTCUSD');

    expect(component.selectedEpic()).toBe('BTCUSD');
  });
});
