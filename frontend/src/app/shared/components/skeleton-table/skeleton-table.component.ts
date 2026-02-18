import { Component, ChangeDetectionStrategy, input } from '@angular/core';
import { PlaceholderDirective, PlaceholderAnimationDirective } from '@coreui/angular';
import { TableDirective } from '@coreui/angular';

@Component({
  selector: 'app-skeleton-table',
  standalone: true,
  imports: [
    PlaceholderDirective,
    PlaceholderAnimationDirective,
    TableDirective,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <table cTable [small]="true" class="mb-0" cPlaceholderAnimation="wave">
      <thead>
        <tr>
          @for (_ of columnsArray; track $index) {
            <th>
              <span cPlaceholder class="skeleton-header" [style.width]="headerWidths[$index % headerWidths.length]"></span>
            </th>
          }
        </tr>
      </thead>
      <tbody>
        @for (_ of rowsArray; track $index) {
          <tr>
            @for (__ of columnsArray; track $index) {
              <td>
                <span cPlaceholder class="skeleton-cell" [style.width]="cellWidths[($index + _) % cellWidths.length]"></span>
              </td>
            }
          </tr>
        }
      </tbody>
    </table>
  `,
  styles: [`
    .skeleton-header,
    .skeleton-cell {
      display: inline-block;
      height: 0.625rem;
      border-radius: 3px;
    }
    .skeleton-header {
      height: 0.5rem;
    }
    :host ::ng-deep .placeholder {
      background-color: var(--mantis-surface-4, #21262d) !important;
      opacity: 0.6;
    }
  `]
})
export class SkeletonTableComponent {
  readonly columns = input(5);
  readonly rowCount = input(5);

  readonly headerWidths = ['60%', '50%', '70%', '45%', '55%'];
  readonly cellWidths = ['75%', '55%', '85%', '40%', '65%', '50%', '70%'];

  get columnsArray(): number[] {
    return Array.from({ length: this.columns() });
  }

  get rowsArray(): number[] {
    return Array.from({ length: this.rowCount() });
  }
}
