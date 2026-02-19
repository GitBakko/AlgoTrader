import {
  Component, ChangeDetectionStrategy, input, output,
} from '@angular/core';
import { ButtonDirective, SpinnerComponent } from '@coreui/angular';

/**
 * Reusable button that shows an inline spinner and disables itself
 * while an async operation is in progress.
 *
 * Usage:
 *   <app-loading-button color="danger" size="sm" [loading]="closing()"
 *                        (clicked)="closePosition(id)">
 *     Chiudi
 *   </app-loading-button>
 */
@Component({
  selector: 'app-loading-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ButtonDirective, SpinnerComponent],
  template: `
    <button cButton
            [color]="color()"
            [size]="size()"
            [variant]="variant()"
            [type]="type()"
            [disabled]="disabled() || loading()"
            (click)="onClick($event)">
      @if (loading()) {
        <c-spinner size="sm" class="me-1"></c-spinner>
      }
      <ng-content />
    </button>
  `,
  styles: [`
    :host { display: inline-block; }
    button[disabled] { cursor: not-allowed; opacity: 0.65; }
  `],
})
export class LoadingButtonComponent {
  readonly loading = input(false);
  readonly disabled = input(false);
  readonly color = input<string>('primary');
  readonly size = input<string>('sm');
  readonly variant = input<'ghost' | 'outline' | undefined>(undefined);
  readonly type = input<'button' | 'submit' | 'reset'>('button');

  readonly clicked = output<MouseEvent>();

  onClick(event: MouseEvent): void {
    if (!this.loading() && !this.disabled()) {
      this.clicked.emit(event);
    }
  }
}
