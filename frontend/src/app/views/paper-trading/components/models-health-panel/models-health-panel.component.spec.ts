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

  it('renders 21 cells in grid', () => {
    const cells = fixture.debugElement.queryAll(By.css('.pv-mh__cell'));
    expect(cells.length).toBe(21);
  });

  it('renders ML MODELS header label', () => {
    const label = fixture.debugElement.query(By.css('.pv-mh__label')).nativeElement as HTMLElement;
    expect(label.textContent?.trim()).toBe('ML MODELS');
  });

  it('renders badge as loaded/total with check when fully loaded', () => {
    const badge = fixture.debugElement.query(By.css('.pv-mh__badge')).nativeElement as HTMLElement;
    expect(badge.textContent?.replace(/\s+/g, ' ').trim()).toBe('21/21 ✓');
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
        { epic: 'XAUUSD', status: 'ok' as const, accent: '#FFD700' },
        { epic: 'BTCUSD', status: 'missing' as const, accent: '#F7931A' },
        { epic: 'TSLA',   status: 'stale' as const, accent: '#E31937' },
      ],
    };
    fixture.componentRef.setInput('health', mixed);
    fixture.detectChanges();
    const cells = fixture.debugElement.queryAll(By.css('.pv-mh__cell'));
    expect(cells[0].nativeElement.getAttribute('data-status')).toBe('ok');
    expect(cells[1].nativeElement.getAttribute('data-status')).toBe('missing');
    expect(cells[2].nativeElement.getAttribute('data-status')).toBe('stale');
  });

  it('renders 3-letter ticker per cell', () => {
    fixture.componentRef.setInput('health', {
      loaded: 1, total: 1,
      perAsset: [{ epic: 'XAUUSD', status: 'ok' as const }],
    });
    fixture.detectChanges();
    const ticker = fixture.debugElement.query(By.css('.pv-mh__cell-ticker')).nativeElement as HTMLElement;
    expect(ticker.textContent?.trim()).toBe('XAU');
  });

  it('renders footer meta when present', () => {
    fixture.componentRef.setInput('health', {
      ...baseHealth,
      meta: { features: 199, version: 'v1', lastTrained: '26/04/26' },
    });
    fixture.detectChanges();
    const foot = fixture.debugElement.query(By.css('.pv-mh__foot')).nativeElement as HTMLElement;
    expect(foot.textContent).toContain('199 features');
    expect(foot.textContent).toContain('v1');
    expect(foot.textContent).toContain('26/04/26');
  });
});
