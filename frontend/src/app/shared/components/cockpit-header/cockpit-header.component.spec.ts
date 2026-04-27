import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { CockpitHeaderComponent } from './cockpit-header.component';

describe('CockpitHeaderComponent', () => {
  let fixture: ComponentFixture<CockpitHeaderComponent>;
  let component: CockpitHeaderComponent;

  const toggleBtn = (): HTMLButtonElement =>
    fixture.debugElement.query(By.css('button[data-action]')).nativeElement as HTMLButtonElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [CockpitHeaderComponent] }).compileComponents();
    fixture = TestBed.createComponent(CockpitHeaderComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('pageTitle', 'Paper Trading');
    fixture.detectChanges();
  });

  it('renders page title', () => {
    const title = fixture.debugElement.query(By.css('.cockpit-header__title')).nativeElement as HTMLElement;
    expect(title.textContent?.trim()).toBe('Paper Trading');
  });

  it('renders default IDLE state pill', () => {
    const pill = fixture.debugElement.query(By.css('.cockpit-header__pill--state')).nativeElement as HTMLElement;
    expect(pill.getAttribute('data-state')).toBe('IDLE');
  });

  it('renders DEMO mode pill by default', () => {
    const pill = fixture.debugElement.query(By.css('.cockpit-header__pill--mode')).nativeElement as HTMLElement;
    expect(pill.getAttribute('data-mode')).toBe('DEMO');
    expect(pill.textContent?.trim()).toBe('DEMO');
  });

  it('renders RUNNING state when input set', () => {
    fixture.componentRef.setInput('state', 'RUNNING');
    fixture.detectChanges();
    const pill = fixture.debugElement.query(By.css('.cockpit-header__pill--state')).nativeElement as HTMLElement;
    expect(pill.getAttribute('data-state')).toBe('RUNNING');
  });

  it('formats lastTickAgo under 60s', () => {
    fixture.componentRef.setInput('lastTickAgo', 1.2);
    fixture.detectChanges();
    expect(component.tickLabel()).toBe('1.2s');
  });

  it('formats lastTickAgo above 60s', () => {
    fixture.componentRef.setInput('lastTickAgo', 125);
    fixture.detectChanges();
    expect(component.tickLabel()).toBe('2m 5s');
  });

  it('renders START label and primary variant when state is IDLE', () => {
    const btn = toggleBtn();
    expect(btn.textContent?.trim()).toBe('START');
    expect(btn.getAttribute('data-action')).toBe('start');
    expect(btn.classList.contains('cockpit-header__btn--primary')).toBeTrue();
    expect(btn.classList.contains('cockpit-header__btn--warning')).toBeFalse();
    expect(btn.getAttribute('aria-label')).toBe('Start paper trading loop');
  });

  it('renders STOP label and warning variant when state is RUNNING', () => {
    fixture.componentRef.setInput('state', 'RUNNING');
    fixture.detectChanges();
    const btn = toggleBtn();
    expect(btn.textContent?.trim()).toBe('STOP');
    expect(btn.getAttribute('data-action')).toBe('stop');
    expect(btn.classList.contains('cockpit-header__btn--warning')).toBeTrue();
    expect(btn.classList.contains('cockpit-header__btn--primary')).toBeFalse();
    expect(btn.getAttribute('aria-label')).toBe('Stop paper trading loop');
  });

  it('emits stopClicked on toggle button click in IDLE state', () => {
    const spy = jasmine.createSpy('toggle');
    component.stopClicked.subscribe(spy);
    toggleBtn().click();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('emits stopClicked on toggle button click in RUNNING state', () => {
    fixture.componentRef.setInput('state', 'RUNNING');
    fixture.detectChanges();
    const spy = jasmine.createSpy('toggle');
    component.stopClicked.subscribe(spy);
    toggleBtn().click();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('emits emergencyClicked on KILL SWITCH button click', () => {
    const spy = jasmine.createSpy('emergency');
    component.emergencyClicked.subscribe(spy);
    const btn = fixture.debugElement.query(By.css('.cockpit-header__btn--kill')).nativeElement as HTMLButtonElement;
    expect(btn.textContent?.trim()).toBe('KILL SWITCH');
    btn.click();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('renders Stopping… label when emergencyBusy is true', () => {
    fixture.componentRef.setInput('emergencyBusy', true);
    fixture.detectChanges();
    const btn = fixture.debugElement.query(By.css('.cockpit-header__btn--kill')).nativeElement as HTMLButtonElement;
    expect(btn.textContent?.trim()).toBe('Stopping…');
    expect(btn.disabled).toBeTrue();
  });

  it('does not emit toggle when stopBusy is true', () => {
    const spy = jasmine.createSpy('toggle');
    component.stopClicked.subscribe(spy);
    fixture.componentRef.setInput('stopBusy', true);
    fixture.detectChanges();
    const btn = toggleBtn();
    btn.click();
    expect(spy).not.toHaveBeenCalled();
    expect(btn.disabled).toBeTrue();
  });
});
