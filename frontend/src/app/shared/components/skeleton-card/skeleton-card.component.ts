import { Component, ChangeDetectionStrategy, input } from '@angular/core';
import { CardComponent, CardBodyComponent, CardHeaderComponent } from '@coreui/angular';
import { PlaceholderDirective, PlaceholderAnimationDirective } from '@coreui/angular';

@Component({
  selector: 'app-skeleton-card',
  standalone: true,
  imports: [
    CardComponent,
    CardBodyComponent,
    CardHeaderComponent,
    PlaceholderDirective,
    PlaceholderAnimationDirective,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <c-card class="border-top border-top-3 border-top-primary h-100">
      @if (showHeader()) {
        <c-card-header class="py-2">
          <span cPlaceholderAnimation="wave">
            <span cPlaceholder cPlaceholderSize="sm" class="skeleton-line" style="width:40%"></span>
          </span>
        </c-card-header>
      }
      <c-card-body class="p-3" cPlaceholderAnimation="wave">
        @for (_ of rowsArray; track $index) {
          <span
            cPlaceholder
            class="skeleton-line mb-2"
            [style.width]="widths[$index % widths.length]"
          ></span>
        }
      </c-card-body>
    </c-card>
  `,
  styles: [`
    .skeleton-line {
      display: block;
      height: 0.75rem;
      border-radius: var(--mantis-radius-sm);
    }
    :host ::ng-deep .placeholder {
      background-color: var(--mantis-surface-4, #21262d) !important;
      opacity: 0.6;
    }
  `]
})
export class SkeletonCardComponent {
  readonly rows = input(3);
  readonly showHeader = input(true);

  readonly widths = ['85%', '70%', '55%', '90%', '60%'];

  get rowsArray(): number[] {
    return Array.from({ length: this.rows() });
  }
}
