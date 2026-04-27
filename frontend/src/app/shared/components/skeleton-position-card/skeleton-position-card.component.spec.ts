import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { SkeletonPositionCardComponent } from './skeleton-position-card.component';

describe('SkeletonPositionCardComponent', () => {
  let fixture: ComponentFixture<SkeletonPositionCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [SkeletonPositionCardComponent] }).compileComponents();
    fixture = TestBed.createComponent(SkeletonPositionCardComponent);
    fixture.detectChanges();
  });

  it('renders the shimmer card with the expected sections', () => {
    const host = fixture.debugElement.query(By.css('.pos-skel')).nativeElement as HTMLElement;
    expect(host).not.toBeNull();
    expect(host.getAttribute('role')).toBe('status');
    expect(fixture.nativeElement.querySelector('.pos-skel__triplet')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.pos-skel__pnl')).not.toBeNull();
  });

  it('renders three triplet cells matching the SL/Entry/TP layout', () => {
    const cells = fixture.nativeElement.querySelectorAll('.pos-skel__triplet-cell');
    expect(cells.length).toBe(3);
  });
});
