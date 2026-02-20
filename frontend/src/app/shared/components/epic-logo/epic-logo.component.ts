/**
 * Epic Logo Component - Display asset logos with loading state
 * Uses LogoService to fetch logos from CoinGecko/Brandfetch with emoji fallback
 */

import { Component, Input, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogoService } from '../../../core/services/logo.service';

@Component({
  selector: 'app-epic-logo',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="epic-logo-wrapper" [style.width.px]="size" [style.height.px]="size">
      @if (loading()) {
        <div class="logo-skeleton" [style.width.px]="size" [style.height.px]="size"></div>
      } @else if (logoUrl()) {
        <img
          [src]="logoUrl()"
          [alt]="epic + ' logo'"
          [width]="size"
          [height]="size"
          class="epic-logo"
          [class.rounded]="rounded"
          (error)="onError()"
        />
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

    .logo-skeleton {
      background: linear-gradient(
        90deg,
        var(--cui-border-color) 25%,
        var(--cui-body-bg) 50%,
        var(--cui-border-color) 75%
      );
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
      border-radius: 4px;
    }

    @keyframes shimmer {
      0% {
        background-position: 200% 0;
      }
      100% {
        background-position: -200% 0;
      }
    }

    .logo-fallback {
      display: flex;
      align-items: center;
      justify-content: center;
      background-color: var(--cui-primary);
      border-radius: 4px;

      .fallback-text {
        color: white;
        font-weight: 600;
        font-size: 0.75em;
        text-transform: uppercase;
      }
    }

    // Mantis AI theme
    :host-context(.mantis-theme) {
      .logo-fallback {
        background-color: var(--mantis-neon, #39ff14);

        .fallback-text {
          color: var(--mantis-text-on-neon, #0d1117);
        }
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class EpicLogoComponent implements OnInit {
  @Input() epic!: string;
  @Input() size: number = 32;
  @Input() rounded: boolean = false;

  readonly loading = signal(true);
  readonly logoUrl = signal<string | null>(null);

  constructor(private logoService: LogoService) {}

  async ngOnInit(): Promise<void> {
    if (!this.epic) {
      this.loading.set(false);
      return;
    }

    try {
      const url = await this.logoService.getLogoUrl(this.epic);
      this.logoUrl.set(url);
    } catch (error) {
      console.warn(`Failed to load logo for ${this.epic}:`, error);
    } finally {
      this.loading.set(false);
    }
  }

  onError(): void {
    // On image load error, clear URL to show fallback
    this.logoUrl.set(null);
  }
}
