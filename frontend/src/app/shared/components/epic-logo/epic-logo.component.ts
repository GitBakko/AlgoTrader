/**
 * Epic Logo Component — resilient asset logo with fallback chain.
 *
 * Walks a priority-ordered URL list provided by `LogoService`. On image
 * load error we step to the next entry; the final entry is always an
 * inline SVG emoji that cannot fail. No API calls — every URL points
 * directly at an image, so CORS / rate-limit failures simply fall
 * through to the next source.
 */

import { ChangeDetectionStrategy, Component, Input, OnChanges, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogoService } from '../../../core/services/logo.service';

@Component({
  selector: 'app-epic-logo',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="epic-logo-wrapper" [style.width.px]="size" [style.height.px]="size">
      @if (currentUrl()) {
        <img
          [src]="currentUrl()"
          [alt]="epic + ' logo'"
          [width]="size"
          [height]="size"
          class="epic-logo"
          [class.rounded]="rounded"
          loading="lazy"
          referrerpolicy="no-referrer"
          (error)="onError()" />
      } @else {
        <div class="logo-fallback" [style.width.px]="size" [style.height.px]="size">
          <span class="fallback-text">{{ epic.substring(0, 2) }}</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .epic-logo-wrapper {
      display: inline-block;
      position: relative;
    }

    .epic-logo {
      width: 100%;
      height: 100%;
      object-fit: contain;
      transition: transform 0.2s ease;

      &.rounded {
        border-radius: 50%;
      }

      &:hover {
        transform: scale(1.05);
      }
    }

    .logo-fallback {
      // C5-FE-AUDIT: neon-green is reserved as accent. Was filling the
      // entire 32x32..96x96 fallback box, violating "neon = accent only".
      // Use surface-3 elevation for the box and put neon on the text.
      display: flex;
      align-items: center;
      justify-content: center;
      background-color: var(--mantis-surface-3, #1c2128);
      border: 1px solid var(--mantis-border-accent, rgba(57, 255, 20, 0.18));
      border-radius: var(--mantis-radius-sm, 4px);

      .fallback-text {
        color: var(--mantis-neon, #39ff14);
        font-weight: 700;
        font-size: 0.75em;
        text-transform: uppercase;
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EpicLogoComponent implements OnChanges {
  @Input() epic!: string;
  @Input() size = 32;
  @Input() rounded = false;

  private urlChain: string[] = [];
  private chainIndex = 0;
  readonly currentUrl = signal<string | null>(null);

  constructor(private logoService: LogoService) {}

  ngOnChanges(): void {
    if (!this.epic) {
      this.currentUrl.set(null);
      return;
    }
    this.urlChain = this.logoService.getLogoUrls(this.epic);
    this.chainIndex = 0;
    this.currentUrl.set(this.urlChain[0] ?? null);
  }

  onError(): void {
    this.chainIndex += 1;
    if (this.chainIndex < this.urlChain.length) {
      this.currentUrl.set(this.urlChain[this.chainIndex]);
    } else {
      this.currentUrl.set(null);
    }
  }
}
