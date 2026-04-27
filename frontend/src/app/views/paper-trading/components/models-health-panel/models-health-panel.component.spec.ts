import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { ModelsHealthPanelComponent } from './models-health-panel.component';
import type { ModelsHealth } from '../../../../core/models/paper-trading';

const baseHealth: ModelsHealth = {
  loaded: 21,
  total: 21,
  perAsset: Array.from({ length: 21 }, (_, i) => ({ epic: `E${i}`, status: 'ok' as const })),
};

describe('ModelsHealthPanelComponent', () => {
  let fixture: ComponentFixture<ModelsHealthPanelComponent>;
  let component: ModelsHealthPanelComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ModelsHealthPanelComponent] }).compileComponents();
    fixture = TestBed.createComponent(ModelsHealthPanelComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('health', baseHealth);
    fixture.detectChanges();
  });

  it('renders 21 dots in grid', () => {
    const dots = fixture.debugElement.queryAll(By.css('.pv-mh__dot'));
    expect(dots.length).toBe(21);
  });

  it('renders badge as loaded/total', () => {
    const badge = fixture.debugElement.query(By.css('.pv-mh__badge')).nativeElement as HTMLElement;
    expect(badge.textContent?.trim()).toBe('21/21');
    expect(badge.classList).toContain('is-ok');
  });

  it('marks badge is-missing when loaded is 0', () => {
    fixture.componentRef.setInput('health', { ...baseHealth, loaded: 0 });
    fixture.detectChanges();
    expect(component.badgeClass()).toBe('is-missing');
  });

  it('marks badge is-partial when loaded is between 0 and total', () => {
    fixture.componentRef.setInput('health', { ...baseHealth, loaded: 12 });
    fixture.detectChanges();
    expect(component.badgeClass()).toBe('is-partial');
  });

  it('encodes per-asset status into data-status attribute', () => {
    const mixed = {
      ...baseHealth,
      perAsset: [
        { epic: 'A', status: 'ok' as const },
        { epic: 'B', status: 'missing' as const },
        { epic: 'C', status: 'stale' as const },
      ],
    };
    fixture.componentRef.setInput('health', mixed);
    fixture.detectChanges();
    const dots = fixture.debugElement.queryAll(By.css('.pv-mh__dot'));
    expect(dots[0].nativeElement.getAttribute('data-status')).toBe('ok');
    expect(dots[1].nativeElement.getAttribute('data-status')).toBe('missing');
    expect(dots[2].nativeElement.getAttribute('data-status')).toBe('stale');
  });
});
