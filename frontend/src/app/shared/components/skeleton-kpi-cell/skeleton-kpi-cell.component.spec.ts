import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { SkeletonKpiCellComponent } from './skeleton-kpi-cell.component';

describe('SkeletonKpiCellComponent', () => {
  let fixture: ComponentFixture<SkeletonKpiCellComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [SkeletonKpiCellComponent] }).compileComponents();
    fixture = TestBed.createComponent(SkeletonKpiCellComponent);
  });

  it('renders the shimmer host and exposes a status role', () => {
    fixture.detectChanges();
    const host = fixture.debugElement.query(By.css('.kpi-skel')).nativeElement as HTMLElement;
    expect(host.getAttribute('role')).toBe('status');
    expect(host.getAttribute('data-accent')).toBe('neutral');
  });

  it('does not render the sparkline placeholder by default', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.kpi-skel__spark')).toBeNull();
  });

  it('renders the sparkline placeholder when showSpark is true', () => {
    fixture.componentRef.setInput('showSpark', true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.kpi-skel__spark')).not.toBeNull();
  });

  it('reflects accent variant on the data-accent attribute', () => {
    fixture.componentRef.setInput('accent', 'profit');
    fixture.detectChanges();
    const host = fixture.debugElement.query(By.css('.kpi-skel')).nativeElement as HTMLElement;
    expect(host.getAttribute('data-accent')).toBe('profit');
  });
});
